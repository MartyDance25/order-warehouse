"""打开沙箱里的 DuckDB，并装入或重置模拟数据。"""

from __future__ import annotations

import re
import time
from pathlib import Path

import duckdb

from warehouse.seed import load_seed
from warehouse.sqlutil import quote_ident

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
MAX_SESSION_FILES = 24
MAX_SESSION_AGE_SECONDS = 24 * 3600
MAX_SESSION_BYTES = 200 * 1024 * 1024


class SandboxError(RuntimeError):
    """安全限制没有生效，不能继续执行学员 SQL。"""


def _setting(con: duckdb.DuckDBPyConnection, name: str) -> str:
    row = con.execute("SELECT current_setting(?)", [name]).fetchone()
    return "" if row is None or row[0] is None else str(row[0])


def _is_false(value: str) -> bool:
    return value.strip().lower() in {"0", "false", "off"}


def _is_true(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "on"}


def sandbox(con: duckdb.DuckDBPyConnection) -> None:
    if not _is_false(_setting(con, "enable_external_access")):
        raise SandboxError("外部文件访问没有关闭。")
    con.execute("SET memory_limit='256MB'")
    con.execute("SET threads=2")
    con.execute("SET max_execution_time=8000")
    if int(float(_setting(con, "max_execution_time") or "0")) <= 0:
        raise SandboxError("查询时间限制没有生效。")
    con.execute("SET lock_configuration=true")
    if not _is_true(_setting(con, "lock_configuration")):
        raise SandboxError("数据库配置锁没有生效。")
    try:
        con.execute("SELECT getenv('PATH')").fetchall()
    except duckdb.Error:
        return
    raise SandboxError("环境变量函数仍然可以执行。")


def open_database(path: str | Path) -> duckdb.DuckDBPyConnection:
    if str(path) == ":memory:":
        con = duckdb.connect(":memory:", config={"enable_external_access": False})
    else:
        file_path = Path(path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        con = duckdb.connect(str(file_path), config={"enable_external_access": False})
    sandbox(con)
    if not table_exists(con, "ods_order"):
        load_seed(con)
    return con


def table_exists(con: duckdb.DuckDBPyConnection, name: str) -> bool:
    row = con.execute(
        """
        SELECT COUNT(*)
        FROM information_schema.tables
        WHERE table_schema = 'main' AND table_name = ?
        """,
        [name],
    ).fetchone()
    return bool(row and row[0])


def list_tables(con: duckdb.DuckDBPyConnection) -> list[str]:
    rows = con.execute(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'main' AND table_type = 'BASE TABLE'
        ORDER BY table_name
        """
    ).fetchall()
    return [row[0] for row in rows]


def reset_database(con: duckdb.DuckDBPyConnection) -> None:
    rows = con.execute(
        """
        SELECT table_name, table_type
        FROM information_schema.tables
        WHERE table_schema = 'main'
        """
    ).fetchall()
    for name, table_type in rows:
        if not _IDENT.fullmatch(name):
            continue
        kind = "VIEW" if table_type == "VIEW" else "TABLE"
        con.execute(f"DROP {kind} IF EXISTS {quote_ident(name)}")
    load_seed(con)


def delete_session_files(path: Path) -> None:
    path.unlink(missing_ok=True)
    Path(str(path) + ".wal").unlink(missing_ok=True)
    path.with_suffix(".progress.json").unlink(missing_ok=True)


def enforce_session_quota(root: Path, keep: Path) -> None:
    """限制会话库的个数、大小和保存时间，避免文件无限堆积。"""
    root.mkdir(parents=True, exist_ok=True)
    keep_resolved = keep.resolve()
    now = time.time()
    for path in list(root.glob("*.duckdb")):
        if path.resolve() == keep_resolved:
            continue
        try:
            if now - path.stat().st_mtime > MAX_SESSION_AGE_SECONDS:
                delete_session_files(path)
        except OSError:
            continue

    def others() -> list[Path]:
        found = []
        for path in root.glob("*.duckdb"):
            try:
                if path.resolve() != keep_resolved:
                    found.append(path)
            except OSError:
                continue
        found.sort(key=lambda item: item.stat().st_mtime)
        return found

    def total_bytes() -> int:
        total = 0
        for path in root.glob("*.duckdb"):
            try:
                total += path.stat().st_size
            except OSError:
                continue
            wal = Path(str(path) + ".wal")
            if wal.exists():
                try:
                    total += wal.stat().st_size
                except OSError:
                    continue
        return total

    removable = others()
    while removable and (len(list(root.glob("*.duckdb"))) > MAX_SESSION_FILES or total_bytes() > MAX_SESSION_BYTES):
        delete_session_files(removable.pop(0))


def drop_table(con: duckdb.DuckDBPyConnection, name: str) -> None:
    if not _IDENT.fullmatch(name):
        raise ValueError("非法表名")
    if name.startswith(("ods_", "dim_")):
        raise ValueError("不能删除贴源表或维度表")
    con.execute(f"DROP TABLE IF EXISTS {quote_ident(name)}")
