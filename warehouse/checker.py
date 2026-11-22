"""用标准结果集验收学员结果。除排行榜外，行顺序不同也可以通过。"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

import pandas as pd

from warehouse.db import open_database
from warehouse.diagnose import LABELS, as_number, diagnose, is_null, show
from warehouse.exercises import EXERCISES, Exercise, get_exercise
from warehouse.runner import RunResult, execute_student_sql
from warehouse.sqlutil import quote_ident, split_sql

_BY_ID = {exercise.id: exercise for exercise in EXERCISES}


@dataclass
class CheckResult:
    passed: bool
    messages: list[str]
    raw_error: str = ""
    row_count: int = 0
    expected_count: int = 0
    frame: pd.DataFrame | None = None
    run_ok: bool = False


def _column_kind(values: list) -> str:
    kinds = set()
    for value in values:
        if is_null(value):
            continue
        if isinstance(value, (datetime, pd.Timestamp)):
            kinds.add("ts" if _has_clock(value) else "date")
        elif isinstance(value, date):
            kinds.add("date")
        elif isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
            kinds.add("num")
        else:
            kinds.add("str")
    if kinds == {"num"}:
        return "num"
    if "ts" in kinds:
        return "ts"
    if kinds == {"date"}:
        return "date"
    return "str"


def _has_clock(value) -> bool:
    if isinstance(value, pd.Timestamp):
        value = value.to_pydatetime()
    return isinstance(value, datetime) and not (value.hour == value.minute == value.second == 0 and value.microsecond == 0)


def _canonical(value, kind: str):
    if is_null(value):
        return ("null",)
    if isinstance(value, pd.Timestamp):
        value = value.to_pydatetime()
    if kind == "num":
        number = as_number(value)
        if number is None or (isinstance(number, float) and math.isnan(number)):
            return ("bad", show(value))
        return ("num", round(number, 2))
    if kind == "date":
        if isinstance(value, datetime):
            return ("date", value.date().isoformat())
        if isinstance(value, date):
            return ("date", value.isoformat())
        text = str(value).strip()
        if len(text) >= 10 and text[4] == "-" and text[7] == "-":
            return ("date", text[:10])
        return ("bad", text)
    if kind == "ts":
        if isinstance(value, datetime):
            return ("ts", value.strftime("%Y-%m-%d %H:%M:%S"))
        text = str(value).strip().replace("T", " ")
        return ("ts", text[:19])
    return ("str", str(value).strip())


def _normalize_frame(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out.columns = [str(name).lower() for name in out.columns]
    return out


def _rows(frame: pd.DataFrame, columns: list[str], kinds: dict[str, str]) -> list[tuple]:
    records = frame.to_dict("records") if not frame.empty else []
    return [tuple(_canonical(row.get(column), kinds[column]) for column in columns) for row in records]


def _index(frame: pd.DataFrame, keys: tuple[str, ...], kinds: dict[str, str]) -> tuple[dict, list]:
    indexed = {}
    duplicates = []
    if frame.empty and not keys:
        return indexed, duplicates
    for row in frame.to_dict("records"):
        key = tuple(_canonical(row.get(column), kinds[column]) for column in keys)
        if key in indexed:
            duplicates.append(key)
        else:
            indexed[key] = row
    return indexed, duplicates


def _format_key(keys: tuple[str, ...], key, row: dict | None = None) -> str:
    parts = []
    for name, value in zip(keys, key):
        shown = value[1] if isinstance(value, tuple) and len(value) > 1 else show(value)
        parts.append(f"{LABELS.get(name, name)} {shown}")
    if row is not None and "sku_name" in row and "sku_name" not in keys:
        parts.append(show(row.get("sku_name")))
    return "，".join(parts)


def build_expected(exercise: Exercise) -> pd.DataFrame:
    con = open_database(":memory:")
    try:
        pending = list(exercise.ref_deps) + [exercise.id]
        done = set()
        for exercise_id in pending:
            if exercise_id in done:
                continue
            done.add(exercise_id)
            current = get_exercise(exercise_id)
            if not current.reference_sql:
                continue
            for statement in split_sql(current.reference_sql):
                con.execute(statement)
        if not exercise.target_table:
            return pd.DataFrame()
        frame = con.execute(f"SELECT * FROM {quote_ident(exercise.target_table)}").fetchdf()
        if exercise.order_sensitive:
            ordered = con.execute(
                f"SELECT * FROM {quote_ident(exercise.target_table)} ORDER BY rowid"
            ).fetchdf()
            return ordered
        return frame
    finally:
        con.close()


def _physical_frame(con, table_name: str) -> pd.DataFrame:
    return con.execute(f"SELECT * FROM {quote_ident(table_name)} ORDER BY rowid").fetchdf()


def compare_frames(exercise: Exercise, student: pd.DataFrame, expected: pd.DataFrame) -> list[str]:
    student = _normalize_frame(student)
    expected = _normalize_frame(expected)
    required = [name for name, _ in exercise.columns]
    missing = [name for name in required if name not in student.columns]
    messages: list[str] = []
    if missing:
        messages.append("缺少字段：" + "、".join(missing) + "。请对照目标表结构补齐。")
    present = [name for name in required if name in student.columns]
    if not present:
        return messages or ["结果里没有目标字段。"]

    kinds = {column: _column_kind(expected[column].tolist()) for column in present if column in expected.columns}
    for column in present:
        kinds.setdefault(column, "str")

    student_view = student[present]
    expected_view = expected[present]
    pitfall_messages = diagnose(exercise, student, expected)

    if exercise.order_sensitive and not missing:
        got_rows = _rows(student_view, present, kinds)
        exp_rows = _rows(expected_view, present, kinds)
        if got_rows == exp_rows:
            return []
        if sorted(got_rows) == sorted(exp_rows):
            messages.append("名次和金额是对的，但行顺序不是按统计日期、名次排列。请在 SQL 最后加上 ORDER BY stat_date, rank_no。")
            return pitfall_messages + messages

    got_sorted = sorted(_rows(student_view, present, kinds))
    exp_sorted = sorted(_rows(expected_view, present, kinds))
    if not exercise.order_sensitive and got_sorted == exp_sorted and not missing:
        return []

    if len(student_view) != len(expected_view):
        messages.append(f"结果共 {len(student_view)} 行，预期 {len(expected_view)} 行。")

    if exercise.keys and all(key in present for key in exercise.keys):
        got_index, duplicates = _index(student_view, exercise.keys, kinds)
        exp_index, _ = _index(expected_view, exercise.keys, kinds)
        if duplicates:
            messages.append("同一个粒度出现了多行。请检查 JOIN 是否把一条记录放大了。")
        missing_keys = [key for key in exp_index if key not in got_index]
        extra_keys = [key for key in got_index if key not in exp_index]
        for key in missing_keys[:3]:
            messages.append("缺少 " + _format_key(exercise.keys, key, exp_index[key]) + "。")
        for key in extra_keys[:3]:
            messages.append("多了 " + _format_key(exercise.keys, key, got_index[key]) + "。")
        if len(missing_keys) > 3:
            messages.append(f"另外还有 {len(missing_keys) - 3} 行缺失。")
        compared = 0
        for key, expected_row in exp_index.items():
            actual_row = got_index.get(key)
            if actual_row is None:
                continue
            for column in present:
                if column in exercise.keys:
                    continue
                if _canonical(actual_row.get(column), kinds[column]) == _canonical(expected_row.get(column), kinds[column]):
                    continue
                label = LABELS.get(column, column)
                messages.append(
                    f"{_format_key(exercise.keys, key, expected_row)} 的{label}预期 {show(expected_row.get(column))}，你的结果是 {show(actual_row.get(column))}。"
                )
                compared += 1
                if compared >= 3:
                    break
            if compared >= 3:
                break

    messages = pitfall_messages + messages
    deduped = []
    for message in messages:
        if message not in deduped:
            deduped.append(message)
    if not deduped:
        deduped.append("结果和标准口径不一致。请对照统计口径检查过滤条件、日期和聚合。")
    return deduped[:8]


def check_sql(con, exercise: Exercise, sql: str) -> CheckResult:
    if exercise.kind != "sql":
        return CheckResult(False, ["这道题不使用 SQL 编辑器。"], run_ok=False)
    run: RunResult = execute_student_sql(con, sql, exercise.target_table or None)
    if not run.ok or run.frame is None:
        return CheckResult(False, [run.chinese or "执行没有成功。"], run.raw_error, run_ok=False)
    if exercise.order_sensitive and exercise.target_table:
        student_frame = _physical_frame(con, exercise.target_table)
    else:
        student_frame = run.frame
    expected = build_expected(exercise)
    messages = compare_frames(exercise, student_frame, expected)
    if messages:
        return CheckResult(
            False,
            messages,
            row_count=len(student_frame),
            expected_count=len(expected),
            frame=student_frame,
            run_ok=True,
        )
    order_text = "行内容和顺序都与标准结果一致。" if exercise.order_sensitive else "与标准结果一致，行顺序不同也可以通过。"
    extra = ""
    required = {name for name, _ in exercise.columns}
    extras = [name for name in student_frame.columns if str(name).lower() not in required]
    if extras:
        extra = " 多写的列不参与判题。"
    return CheckResult(
        True,
        [f"通过。{exercise.target_table} 共 {len(student_frame)} 行，{order_text}{extra} 后面的题目可以使用这张表。"],
        row_count=len(student_frame),
        expected_count=len(expected),
        frame=student_frame,
        run_ok=True,
    )
