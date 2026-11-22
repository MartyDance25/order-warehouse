"""在沙箱连接上执行学员 SQL。"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from warehouse.db import table_exists
from warehouse.errors import explain_error
from warehouse.sqlutil import QUERY_HEADS, guard_sql, leading_keyword, quote_ident, remove_comments, split_sql

MAX_ROWS = 5000


class RowLimitError(RuntimeError):
    pass


def _fetch_limited(con, sql: str, limit: int = MAX_ROWS) -> pd.DataFrame:
    cursor = con.execute(sql)
    columns = [item[0] for item in (cursor.description or [])]
    rows = cursor.fetchmany(limit + 1)
    if len(rows) > limit:
        raise RowLimitError(f"结果超过 {limit} 行。请先聚合，或缩小到题目要求的粒度。")
    return pd.DataFrame(rows, columns=columns)


@dataclass
class RunResult:
    ok: bool
    chinese: str
    raw_error: str
    frame: pd.DataFrame | None
    row_count: int
    table_name: str | None


def _fail(chinese: str, raw: str = "", table_name: str | None = None) -> RunResult:
    return RunResult(False, chinese, raw or chinese, None, 0, table_name)


def execute_student_sql(
    con,
    sql: str,
    target_table: str | None = None,
) -> RunResult:
    allowed, message = guard_sql(sql)
    if not allowed:
        return _fail(message, message, target_table)

    statements = [stmt for stmt in split_sql(sql) if remove_comments(stmt).strip()]
    try:
        last_query: str | None = None
        for stmt in statements:
            head = leading_keyword(stmt)
            is_last = stmt is statements[-1]
            if head in QUERY_HEADS and is_last and target_table:
                last_query = stmt
                break
            if head in QUERY_HEADS:
                last_query = stmt
                _fetch_limited(con, stmt)
            else:
                con.execute(stmt)

        if target_table:
            if last_query and leading_keyword(statements[-1]) in QUERY_HEADS:
                con.execute(
                    f"CREATE OR REPLACE TABLE {quote_ident(target_table)} AS {statements[-1]}"
                )
            if not table_exists(con, target_table):
                return _fail(
                    f"没有找到目标表 {target_table}。可以只写一条 SELECT，系统会把结果写入这张表；也可以自己写 CREATE TABLE {target_table} AS SELECT。",
                    "",
                    target_table,
                )
            quoted = quote_ident(target_table)
            count = con.execute(
                f"SELECT COUNT(*) FROM (SELECT 1 FROM {quoted} LIMIT {MAX_ROWS + 1})"
            ).fetchone()[0]
            if int(count) > MAX_ROWS:
                con.execute(f"DROP TABLE IF EXISTS {quoted}")
                return _fail(
                    f"结果超过 {MAX_ROWS} 行。请先聚合，或缩小到题目要求的粒度。",
                    "",
                    target_table,
                )
            frame = _fetch_limited(con, f"SELECT * FROM {quoted} LIMIT {MAX_ROWS}")
            shown_table = target_table
        elif last_query:
            frame = _fetch_limited(con, last_query)
            shown_table = None
        else:
            frame = pd.DataFrame()
            shown_table = None

        return RunResult(True, "", "", frame, int(len(frame)), shown_table)
    except RowLimitError as exc:
        return _fail(str(exc), str(exc), target_table)
    except Exception as exc:  # DuckDB raises several error types
        raw = str(exc)
        return _fail(explain_error(raw), raw, target_table)
