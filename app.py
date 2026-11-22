"""数仓实训台。启动后在浏览器里完成从贴源层到运营日报的 SQL 练习。"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pandas as pd
import streamlit as st

from warehouse.catalog import TABLES
from warehouse.checker import check_sql
from warehouse.dashboard import read_daily, read_rank, read_user_daily
from warehouse.db import (
    SandboxError,
    drop_table,
    enforce_session_quota,
    list_tables,
    open_database,
    reset_database,
    table_exists,
)
from warehouse.sqlutil import quote_ident
from warehouse.exercises import EXERCISES, ORDER_GUIDE, exercises_by_layer, get_exercise, student_table_meta
from warehouse.lineage import QUESTIONS, REFERENCE_STEPS, grade_lineage
from warehouse.progress import empty_progress, load_progress, save_progress
from warehouse.runner import execute_student_sql

ROOT = Path(__file__).resolve().parent
CHECKPOINTS = [
    ("2026-03-01", "pay_amt", 1000, "3 月 1 日实付 = O1001 的 400 + O1006 的 600。O1002 未成功的 80 不加。"),
    ("2026-03-03", "refund_amt", 100, "3 月 3 日退款 = O1001 球鞋 100 元。O1007 申请中的 150 元不加。"),
    ("2026-03-03", "pay_amt", 150, "3 月 3 日实付只有 O1007 的 150 元。"),
    ("2026-03-04", "refund_amt", 40, "3 月 4 日退款是 O1004 的水杯 40 元，不是下单日 3 月 2 日。"),
    ("2026-03-05", "pay_amt", 0, "3 月 5 日 O1005 支付失败，实付为 0；订单已经发生，订单数仍是 1。"),
]
HAND_TOTALS = {"order_amt": 1940, "pay_amt": 1760, "refund_amt": 140}


def inject_css() -> None:
    st.markdown(
        """
        <style>
        .block-container {padding-top: 1.1rem; padding-bottom: 3rem; max-width: 1180px;}
        div[data-testid="stSidebar"] {border-right: 1px solid #e3d9c8;}
        blockquote {border-left: 3px solid #0f5f5c; background: #e7f1f0; padding: 0.35rem 0.85rem; color: #14322f;}
        div[data-testid="stExpander"] {border: 1px solid #e3d9c8; background: #fffdf8;}
        </style>
        """,
        unsafe_allow_html=True,
    )


def session_files() -> tuple[Path, Path]:
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx

        ctx = get_script_run_ctx()
        session_id = ctx.session_id if ctx else "local"
    except Exception:
        session_id = "local"
    safe = re.sub(r"[^A-Za-z0-9_-]", "", session_id)[:48] or "local"
    root = Path(os.environ.get("WAREHOUSE_DATA_DIR", ROOT / "data" / "sessions"))
    root.mkdir(parents=True, exist_ok=True)
    return root / f"{safe}.duckdb", root / f"{safe}.progress.json"


def get_connection():
    db_path, progress_path = session_files()
    enforce_session_quota(db_path.parent, db_path)
    conn = st.session_state.get("con")
    if conn is None or st.session_state.get("db_path") != str(db_path):
        try:
            conn = open_database(db_path)
        except SandboxError:
            st.error("实训库没能在安全限制下打开，已停止执行。")
            st.stop()
        st.session_state.con = conn
        st.session_state.db_path = str(db_path)
        st.session_state.progress_path = str(progress_path)
    return conn


def get_progress() -> dict:
    path = Path(st.session_state.progress_path)
    if "progress" not in st.session_state:
        st.session_state.progress = load_progress(path)
    return st.session_state.progress


def persist_progress() -> None:
    save_progress(Path(st.session_state.progress_path), st.session_state.progress)


def display_frame(frame: pd.DataFrame, limit: int = 30) -> pd.DataFrame:
    view = frame.head(limit).copy()
    for column in view.columns:
        series = view[column]
        if pd.api.types.is_datetime64_any_dtype(series):
            continue
        if pd.api.types.is_bool_dtype(series):
            continue
        view[column] = series.map(_display_cell)
    return view


def _display_cell(value):
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime()
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        number = float(value)
        if abs(number - round(number)) < 1e-6:
            return int(round(number))
        return round(number, 2)
    if hasattr(value, "as_tuple") and value.__class__.__name__ == "Decimal":
        number = float(value)
        if abs(number - round(number)) < 1e-6:
            return int(round(number))
        return round(number, 2)
    return value


def _passed(progress: dict, exercise_id: str) -> bool:
    return bool(progress.get("passed", {}).get(exercise_id))


def render_sidebar(progress: dict) -> None:
    st.sidebar.markdown("## 数仓实训台")
    st.sidebar.caption("电商订单 · 贴源层到运营日报")
    done = sum(1 for exercise in EXERCISES if _passed(progress, exercise.id))
    st.sidebar.progress(done / len(EXERCISES), text=f"已通过 {done} / {len(EXERCISES)}")
    st.sidebar.caption("O1001：球拍 300 + 球鞋 100，一次支付 400 元，两天后退款 100 元。")

    page = st.session_state.get("page", "exercise")
    col_a, col_b = st.sidebar.columns(2)
    if col_a.button("练习", width="stretch", type="primary" if page == "exercise" else "secondary"):
        st.session_state.page = "exercise"
        st.rerun()
    if col_b.button("运营看板", width="stretch", type="primary" if page == "dashboard" else "secondary"):
        st.session_state.page = "dashboard"
        st.rerun()

    st.sidebar.markdown("**练习步骤**")
    current = st.session_state.get("exercise_id", EXERCISES[0].id)
    for layer_name, items in exercises_by_layer():
        st.sidebar.caption(layer_name)
        for exercise in items:
            mark = "✓" if _passed(progress, exercise.id) else "·"
            label = f"{mark} {exercise.nav}"
            selected = exercise.id == current and page == "exercise"
            if st.sidebar.button(
                label,
                key=f"nav_{exercise.id}",
                width="stretch",
                type="primary" if selected else "secondary",
            ):
                st.session_state.exercise_id = exercise.id
                st.session_state.page = "exercise"
                st.rerun()

    st.sidebar.markdown("**表目录**")
    con = get_connection()
    names = list_tables(con)
    for table_name, meta in TABLES.items():
        if table_name not in names:
            continue
        if st.sidebar.button(f"{meta['title']}  {table_name}", key=f"tbl_{table_name}", width="stretch"):
            st.session_state.catalog_table = table_name
            st.session_state.page = "catalog"
            st.rerun()
    student_names = [name for name in names if name not in TABLES]
    if student_names:
        st.sidebar.caption("我生成的表")
        for table_name in student_names:
            if st.sidebar.button(table_name, key=f"stu_{table_name}", width="stretch"):
                st.session_state.catalog_table = table_name
                st.session_state.page = "catalog"
                st.rerun()
    else:
        st.sidebar.caption("通过练习后，你生成的表会出现在这里。")

    st.sidebar.divider()
    if st.sidebar.button("重置模拟数据", width="stretch"):
        st.session_state.confirm_reset = True
    if st.session_state.get("confirm_reset"):
        st.sidebar.warning("会清空本会话里写过的 SQL 和生成的表，八笔模拟订单会重新装入。")
        if st.sidebar.button("确认重置", width="stretch"):
            reset_database(get_connection())
            st.session_state.progress = empty_progress()
            persist_progress()
            for exercise in EXERCISES:
                sql_key = f"sql_{exercise.id}"
                if sql_key in st.session_state:
                    st.session_state[sql_key] = exercise.starter_sql
            st.session_state.runs = {}
            st.session_state.confirm_reset = False
            st.session_state.page = "exercise"
            st.session_state.exercise_id = EXERCISES[0].id
            st.rerun()


def render_catalog() -> None:
    table_name = st.session_state.get("catalog_table", "ods_order")
    meta = TABLES.get(table_name) or student_table_meta(table_name)
    st.markdown(f"# {meta['title'] if meta else table_name}")
    st.caption(table_name)
    if meta:
        st.markdown(f"> 一行代表什么：{meta['grain']}")
        field_frame = pd.DataFrame(meta["columns"], columns=["字段", "类型", "说明"])
        st.markdown("**字段说明**")
        st.dataframe(field_frame, width="stretch", hide_index=True)
    con = get_connection()
    if not table_exists(con, table_name):
        st.info("这张表还不存在。完成对应练习并运行 SQL 后，就可以在这里查看。")
        return
    try:
        frame = con.execute(f"SELECT * FROM {quote_ident(table_name)}").fetchdf()
    except ValueError:
        st.error("表名不合法，无法读取。")
        return
    st.markdown(f"**样例数据** · 共 {len(frame)} 行")
    if "order_id" in {str(column).lower() for column in frame.columns}:
        choice = st.selectbox("按订单查看", ["全部", "只看 O1001"], key=f"filter_{table_name}")
        if choice == "只看 O1001":
            column = next(column for column in frame.columns if str(column).lower() == "order_id")
            frame = frame[frame[column].astype(str) == "O1001"]
    st.dataframe(display_frame(frame, limit=100), width="stretch", hide_index=True)
    if st.button("返回当前练习"):
        st.session_state.page = "exercise"
        st.rerun()


def render_result(run_state: dict) -> None:
    st.markdown("### 运行结果")
    if not run_state:
        st.caption("还没有运行。运行后这里显示列名、样例行和行数。")
        return
    if not run_state.get("ok"):
        st.error(run_state.get("chinese") or "执行没有成功。")
        if run_state.get("raw_error"):
            st.caption("数据库原始报错")
            st.code(run_state["raw_error"], language="text")
        return
    frame = run_state.get("frame")
    row_count = run_state.get("row_count", 0)
    columns = list(frame.columns) if frame is not None else []
    table_name = run_state.get("table_name")
    where = f"已写入 {table_name}。" if table_name else "这是查询结果，尚未要求写入目标表。"
    st.caption(f"共 {row_count} 行。{where}列名：{', '.join(map(str, columns)) or '无'}")
    if frame is not None and row_count:
        shown = min(30, row_count)
        st.caption(f"展示前 {shown} 行。")
        st.dataframe(display_frame(frame), width="stretch", hide_index=True)
    elif frame is not None:
        st.info("查询成功，但结果是 0 行。")
    messages = run_state.get("check_messages") or []
    if run_state.get("check_passed") is True:
        st.success(messages[0] if messages else "通过。")
    elif run_state.get("check_passed") is False and messages:
        st.error("还没有通过。")
        for message in messages:
            st.write("· " + message)


def render_sql_exercise(exercise, progress: dict) -> None:
    sql_key = f"sql_{exercise.id}"
    if st.session_state.get("_reset_target") == exercise.id:
        st.session_state[sql_key] = exercise.starter_sql
        st.session_state._reset_target = None
    if sql_key not in st.session_state:
        st.session_state[sql_key] = progress["sql"].get(exercise.id, exercise.starter_sql)

    if exercise.deps:
        missing = [get_exercise(dep).nav for dep in exercise.deps if not _passed(progress, dep)]
        if missing:
            st.warning("建议先通过：" + "、".join(missing) + "。这道题会读取你自己生成的上游表。")

    st.markdown("**题目**")
    st.markdown(exercise.prompt)
    if exercise.caliber:
        st.markdown("**统计口径**")
        st.markdown(exercise.caliber)
    if exercise.columns:
        st.markdown("**目标表结构** · `" + exercise.target_table + "`")
        if exercise.grain:
            st.markdown(f"> {exercise.grain}")
        st.dataframe(
            pd.DataFrame(exercise.columns, columns=["字段", "说明"]),
            width="stretch",
            hide_index=True,
        )
    if exercise.mappings:
        st.markdown("**源字段到目标字段**")
        st.dataframe(
            pd.DataFrame(exercise.mappings, columns=["目标字段", "来源", "规则"]),
            width="stretch",
            hide_index=True,
        )
    if exercise.layer in {"DWD", "DWS", "ADS"} or exercise.id == "e06_pay_dup":
        with st.expander("八笔订单手算底稿", expanded=False):
            st.markdown(ORDER_GUIDE)

    sql = st.text_area("SQL", key=sql_key, height=280, label_visibility="collapsed")
    progress["sql"][exercise.id] = sql

    buttons = st.columns(5)
    run_clicked = buttons[0].button("运行 SQL", type="primary", width="stretch")
    check_clicked = buttons[1].button("提交检查", width="stretch")
    hint_clicked = buttons[2].button("查看提示", width="stretch")
    answer_clicked = buttons[3].button("查看参考答案", width="stretch")
    reset_clicked = buttons[4].button("重置练习", width="stretch")
    if exercise.bad_sql:
        bad_clicked = st.button("运行有问题的 SQL", width="stretch")
    else:
        bad_clicked = False

    runs = st.session_state.setdefault("runs", {})
    con = get_connection()
    if run_clicked:
        result = execute_student_sql(con, sql, exercise.target_table or None)
        runs[exercise.id] = _pack_run(result)
    if bad_clicked:
        result = execute_student_sql(con, exercise.bad_sql, None)
        packed = _pack_run(result)
        packed["note"] = exercise.bad_note
        runs[exercise.id] = packed
    if check_clicked:
        outcome = check_sql(con, exercise, sql)
        packed = runs.get(exercise.id, {})
        if outcome.frame is not None:
            packed = {
                "ok": True,
                "chinese": "",
                "raw_error": "",
                "frame": outcome.frame,
                "row_count": outcome.row_count,
                "table_name": exercise.target_table,
            }
        elif not outcome.run_ok:
            packed = {
                "ok": False,
                "chinese": outcome.messages[0] if outcome.messages else "执行没有成功。",
                "raw_error": outcome.raw_error,
                "frame": None,
                "row_count": 0,
                "table_name": exercise.target_table,
            }
        packed["check_passed"] = outcome.passed
        packed["check_messages"] = outcome.messages
        runs[exercise.id] = packed
        progress["passed"][exercise.id] = bool(outcome.passed)
    if hint_clicked:
        level = int(progress["hints"].get(exercise.id, 0))
        progress["hints"][exercise.id] = min(level + 1, len(exercise.hints))
    if answer_clicked:
        progress["answers_seen"][exercise.id] = True
    if reset_clicked:
        progress["passed"][exercise.id] = False
        progress["hints"][exercise.id] = 0
        progress["answers_seen"][exercise.id] = False
        progress["sql"][exercise.id] = exercise.starter_sql
        if exercise.target_table and table_exists(con, exercise.target_table):
            drop_table(con, exercise.target_table)
        runs.pop(exercise.id, None)
        st.session_state._reset_target = exercise.id
        persist_progress()
        st.rerun()

    level = int(progress["hints"].get(exercise.id, 0))
    if level:
        st.markdown(f"**提示 {level} / {len(exercise.hints)}**")
        for index, hint in enumerate(exercise.hints[:level], start=1):
            st.info(f"{index}. {hint}")
    else:
        st.caption("提示会一步一步出现，不会一次给完。")

    seen = bool(progress["answers_seen"].get(exercise.id))
    with st.expander("参考答案", expanded=seen):
        if seen:
            st.code(exercise.reference_sql, language="sql")
        else:
            st.caption("参考答案默认折叠。需要对照时再点「查看参考答案」。")

    state = runs.get(exercise.id)
    if state and state.get("note") and state.get("ok"):
        st.warning(state["note"])
    render_result(state or {})
    persist_progress()


def _pack_run(result) -> dict:
    return {
        "ok": result.ok,
        "chinese": result.chinese,
        "raw_error": result.raw_error,
        "frame": result.frame,
        "row_count": result.row_count,
        "table_name": result.table_name,
        "check_passed": None,
        "check_messages": [],
    }


def render_lineage(exercise, progress: dict) -> None:
    if st.session_state.get("_reset_lineage"):
        for question in QUESTIONS:
            st.session_state.pop(f"lin_{question.id}", None)
        st.session_state._reset_lineage = False
        st.session_state.lineage_result = None
    st.markdown(exercise.prompt)
    st.markdown("**统计口径**")
    st.markdown(exercise.caliber)
    stored = progress.setdefault("lineage", {})
    answers = {}
    for question in QUESTIONS:
        current = stored.get(question.id, "请选择")
        options = ["请选择", *question.options]
        if current not in options:
            current = "请选择"
        answers[question.id] = st.selectbox(question.prompt, options, index=options.index(current), key=f"lin_{question.id}")
        if answers[question.id] != "请选择":
            stored[question.id] = answers[question.id]

    level = int(progress["hints"].get(exercise.id, 0))
    columns = st.columns([1, 1, 1])
    if columns[0].button("提交检查", type="primary", width="stretch"):
        passed, messages = grade_lineage(stored)
        st.session_state.lineage_result = {"passed": passed, "messages": messages, "show_chain": True}
        progress["passed"][exercise.id] = passed
    if columns[1].button("查看提示", width="stretch"):
        progress["hints"][exercise.id] = min(level + 1, len(exercise.hints))
        level = progress["hints"][exercise.id]
    if columns[2].button("重置练习", width="stretch"):
        progress["lineage"] = {}
        progress["passed"][exercise.id] = False
        progress["hints"][exercise.id] = 0
        st.session_state._reset_lineage = True
        persist_progress()
        st.rerun()

    if level:
        st.markdown(f"**提示 {level} / {len(exercise.hints)}**")
        for index, hint in enumerate(exercise.hints[:level], start=1):
            st.info(f"{index}. {hint}")

    result = st.session_state.get("lineage_result")
    if result:
        if result["passed"]:
            st.success(result["messages"][0])
        else:
            st.error(result["messages"][0])
        if result.get("show_chain"):
            st.markdown("### 参考链路")
            st.caption("这条链路对应支付明细、用户日汇总、运营日报三道题的参考 SQL。")
            for title, detail in REFERENCE_STEPS:
                st.markdown(f"**{title}**")
                st.markdown(detail)
    persist_progress()


def _metric_number(frame: pd.DataFrame, column: str) -> float:
    if frame is None or column not in frame.columns:
        return 0.0
    return float(pd.to_numeric(frame[column], errors="coerce").fillna(0).sum())


def _cell(frame: pd.DataFrame, day: str, column: str):
    if frame is None or column not in frame.columns:
        return None
    dates = frame["stat_date"].astype(str).str.slice(0, 10)
    matched = frame.loc[dates == day, column]
    if matched.empty:
        return None
    value = matched.iloc[0]
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    return float(value)


def render_dashboard() -> None:
    st.markdown("# 运营看板")
    st.caption("看板读取你实际生成的结果表。改完 SQL 并重新运行后，点刷新就能看到数字变化。")
    if st.button("刷新看板"):
        st.rerun()
    con = get_connection()
    daily, daily_message = read_daily(con)
    rank, rank_message = read_rank(con)

    if daily is None:
        st.info(daily_message)
    else:
        order_amt = _metric_number(daily, "order_amt")
        pay_amt = _metric_number(daily, "pay_amt")
        refund_amt = _metric_number(daily, "refund_amt")
        cards = st.columns(4)
        cards[0].metric("下单商品金额", f"{order_amt:.0f} 元", help="各日 order_amt 相加")
        cards[1].metric("实付金额", f"{pay_amt:.0f} 元", help="各日 pay_amt 相加")
        cards[2].metric("退款金额", f"{refund_amt:.0f} 元", help="各日 refund_amt 相加")
        cards[3].metric("实付减退款", f"{pay_amt - refund_amt:.0f} 元")
        st.caption(
            f"手算总账：下单商品金额 {HAND_TOTALS['order_amt']} 元，实付 {HAND_TOTALS['pay_amt']} 元，退款 {HAND_TOTALS['refund_amt']} 元。"
        )
        chart = daily.copy()
        chart["stat_date"] = chart["stat_date"].astype(str).str.slice(0, 10)
        st.bar_chart(chart, x="stat_date", y=["order_amt", "pay_amt", "refund_amt"], height=280)
        st.markdown("**运营日报 ads_ops_daily**")
        st.dataframe(display_frame(daily, limit=50), width="stretch", hide_index=True)

        st.markdown("**手算对照**")
        rows = []
        for day, column, expected, note in CHECKPOINTS:
            actual = _cell(daily, day, column)
            if actual is None:
                judgement = "你的日报里没有这一天或这个字段"
                actual_text = "—"
            elif abs(actual - expected) < 0.02:
                judgement = "和手算一致"
                actual_text = f"{actual:.0f}"
            else:
                judgement = "和手算不一致"
                actual_text = f"{actual:.0f}"
            rows.append(
                {
                    "日期": day,
                    "指标": column,
                    "你的结果": actual_text,
                    "手算": expected,
                    "结论": judgement,
                    "说明": note,
                }
            )
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

    if rank is None:
        st.info(rank_message)
    else:
        st.markdown("**每日商品排行榜 ads_sku_rank_1d**")
        st.dataframe(display_frame(rank, limit=50), width="stretch", hide_index=True)

    try:
        user_daily = read_user_daily(con)
    except Exception as exc:
        user_daily = None
        st.caption("用户日汇总暂时读不出来：" + str(exc).splitlines()[0])
    if user_daily is not None:
        with st.expander("用户日汇总 dws_user_1d", expanded=False):
            st.dataframe(display_frame(user_daily, limit=50), width="stretch", hide_index=True)

    with st.expander("O1001 怎么对手算", expanded=False):
        st.markdown(
            """
O1001 自己的实付是 400 元，退款是 100 元。日报不是按订单展示的，所以 3 月 1 日的实付不会显示成 400。

同一天李娜的 O1006 又支付成功 600 元，未成功的 O1002 不加。因此 3 月 1 日实付 = 400 + 600 = 1000 元。

球鞋退款发生在 3 月 3 日，所以 100 元记在 3 月 3 日的退款里，而不是记回 3 月 1 日。
""".strip()
        )


def render_exercise(progress: dict) -> None:
    exercise = get_exercise(st.session_state.get("exercise_id", EXERCISES[0].id))
    st.markdown(f"# {exercise.title}")
    status = "已通过" if _passed(progress, exercise.id) else "未通过"
    st.caption(f"{exercise.layer_name} · {status}" + (f" · 目标表 {exercise.target_table}" if exercise.target_table else ""))
    if exercise.kind == "lineage":
        render_lineage(exercise, progress)
    else:
        render_sql_exercise(exercise, progress)


def main() -> None:
    st.set_page_config(page_title="数仓实训台", page_icon="📘", layout="wide")
    inject_css()
    st.session_state.setdefault("page", "exercise")
    st.session_state.setdefault("exercise_id", EXERCISES[0].id)
    st.session_state.setdefault("catalog_table", "ods_order")
    get_connection()
    progress = get_progress()
    render_sidebar(progress)
    page = st.session_state.get("page", "exercise")
    if page == "dashboard":
        render_dashboard()
    elif page == "catalog":
        render_catalog()
    else:
        render_exercise(progress)


main()
