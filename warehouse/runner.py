"""在沙箱连接上执行学员 SQL。"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from warehouse.db import table_exists
from warehouse.errors import explain_error
from warehouse.sqlutil import QUERY_HEADS, guard_sql, leading_keyword, quote_ident, remove_comments, split_sql

MAX_ROWS = 5000


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
                con.execute(stmt).fetchdf()
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
            frame = con.execute(f"SELECT * FROM {quote_ident(target_table)}").fetchdf()
            shown_table = target_table
        elif last_query:
            frame = con.execute(last_query).fetchdf()
            shown_table = None
        else:
            frame = pd.DataFrame()
            shown_table = None

        if len(frame) > MAX_ROWS:
            return _fail(
                f"结果有 {len(frame)} 行，超过 {MAX_ROWS} 行。请先聚合，或缩小到题目要求的粒度。",
                "",
                shown_table,
            )
        return RunResult(True, "", "", frame, int(len(frame)), shown_table)
    except Exception as exc:  # DuckDB raises several error types
        raw = str(exc)
        return _fail(explain_error(raw), raw, target_table)
