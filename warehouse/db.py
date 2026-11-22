"""打开沙箱里的 DuckDB，并装入或重置模拟数据。"""

from __future__ import annotations

import re
from pathlib import Path

import duckdb

from warehouse.seed import load_seed
from warehouse.sqlutil import quote_ident

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def sandbox(con: duckdb.DuckDBPyConnection) -> None:
    try:
        con.execute("SET memory_limit='256MB'")
    except duckdb.Error:
        pass
    try:
        con.execute("SET threads=2")
    except duckdb.Error:
        pass
    try:
        con.execute("SET max_execution_time=8000")
    except duckdb.Error:
        pass
    try:
        con.execute("SET lock_configuration=true")
    except duckdb.Error:
        pass


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


def drop_table(con: duckdb.DuckDBPyConnection, name: str) -> None:
    if not _IDENT.fullmatch(name):
        raise ValueError("非法表名")
    if name.startswith(("ods_", "dim_")):
        raise ValueError("不能删除贴源表或维度表")
    con.execute(f"DROP TABLE IF EXISTS {quote_ident(name)}")
