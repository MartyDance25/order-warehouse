"""验收：参考 SQL 能通过，错误 SQL 会给出具体反馈，看板读取学员自己的表。"""

from warehouse.checker import check_sql
from warehouse.dashboard import read_daily, read_rank
from warehouse.db import open_database, reset_database
from warehouse.errors import explain_error
from warehouse.exercises import EXERCISES, get_exercise
from warehouse.lineage import QUESTIONS, grade_lineage
from warehouse.runner import execute_student_sql
from warehouse.sqlutil import guard_sql, split_sql


def _new_db():
    return open_database(":memory:")


def _run_reference_chain(con):
    for exercise in EXERCISES:
        if not exercise.reference_sql:
            continue
        for statement in split_sql(exercise.reference_sql):
            con.execute(statement)


def _amount(frame, day, column):
    dates = frame["stat_date"].astype(str).str.slice(0, 10)
    value = frame.loc[dates == day, column].iloc[0]
    return float(value)


def test_seed_o1001_and_hand_totals():
    con = _new_db()
    _run_reference_chain(con)
    daily, message = read_daily(con)
    assert message == ""
    assert _amount(daily, "2026-03-01", "pay_amt") == 1000
    assert _amount(daily, "2026-03-01", "order_amt") == 1080
    assert _amount(daily, "2026-03-03", "pay_amt") == 150
    assert _amount(daily, "2026-03-03", "refund_amt") == 100
    assert _amount(daily, "2026-03-03", "net_pay_amt") == 50
    assert _amount(daily, "2026-03-04", "refund_amt") == 40
    assert _amount(daily, "2026-03-05", "pay_amt") == 0
    assert _amount(daily, "2026-03-05", "order_cnt") == 1
    assert float(daily["pay_amt"].sum()) == 1760
    assert float(daily["refund_amt"].sum()) == 140
    assert float(daily["order_amt"].sum()) == 1940
    assert daily.loc[daily["stat_date"].astype(str).str.slice(0, 10) == "2026-03-01", "weekday_name"].iloc[0] == "星期日"

    rank, rank_message = read_rank(con)
    assert rank_message == ""
    first = rank.iloc[0]
    assert str(first["stat_date"])[:10] == "2026-03-01"
    assert int(first["rank_no"]) == 1
    assert first["sku_name"] == "羽毛球拍"
    assert float(first["sale_amt"]) == 900

    user = con.execute(
        """
        SELECT refund_amt FROM dws_user_1d
        WHERE user_id = 'U001' AND stat_date = DATE '2026-03-03'
        """
    ).fetchone()[0]
    assert float(user) == 100
    shoe = con.execute(
        """
        SELECT sale_amt, refund_amt FROM dws_sku_1d
        WHERE sku_id = 'SKU102' AND stat_date = DATE '2026-03-03'
        """
    ).fetchone()
    assert float(shoe[0]) == 0
    assert float(shoe[1]) == 100
    con.close()


def test_reference_answers_pass_and_order_does_not_matter():
    con = _new_db()
    for exercise in EXERCISES:
        if exercise.kind != "sql":
            continue
        outcome = check_sql(con, exercise, exercise.reference_sql)
        assert outcome.passed, (exercise.id, outcome.messages)
    e01 = get_exercise("e01_ods_order")
    reversed_sql = """
        SELECT order_id, user_id, shop_id, order_date, order_status_code, item_amount_yuan
        FROM ods_order
        ORDER BY order_id DESC
    """
    outcome = check_sql(con, e01, reversed_sql)
    assert outcome.passed, outcome.messages
    con.close()


def test_bad_join_reports_double_pay():
    con = _new_db()
    exercise = get_exercise("e06_pay_dup")
    outcome = check_sql(con, exercise, exercise.starter_sql)
    assert not outcome.passed
    text = "\n".join(outcome.messages)
    assert "预期实付 400 元，你算出了 800 元" in text
    assert "支付编号" in text
    bad = execute_student_sql(con, exercise.bad_sql, None)
    assert bad.ok
    assert bad.row_count == 2
    assert list(bad.frame["pay_amount_yuan"].astype(float)) == [400.0, 400.0]
    assert set(bad.frame["payment_id"]) == {"P1001"}
    con.close()


def test_payment_unit_and_refund_status_feedback():
    con = _new_db()
    pay = check_sql(con, get_exercise("e04_dwd_pay"), get_exercise("e04_dwd_pay").starter_sql)
    assert not pay.passed
    assert any("400" in message and "分" in message for message in pay.messages)
    refund = check_sql(con, get_exercise("e05_dwd_refund"), get_exercise("e05_dwd_refund").starter_sql)
    assert not refund.passed
    assert any("编码" in message for message in refund.messages)
    con.close()


def test_rank_order_is_required():
    con = _new_db()
    exercise = get_exercise("e11_ads_rank")
    for dep in ("e03_dwd_item", "e05_dwd_refund", "e08_dws_sku"):
        check_sql(con, get_exercise(dep), get_exercise(dep).reference_sql)
    wrong_order = exercise.reference_sql.replace(
        "ORDER BY stat_date, rank_no",
        "ORDER BY stat_date DESC, rank_no DESC",
    )
    outcome = check_sql(con, exercise, wrong_order)
    assert not outcome.passed
    assert any("顺序" in message for message in outcome.messages)
    con.close()


def test_syntax_error_and_guard():
    con = _new_db()
    result = execute_student_sql(con, "SELEC 1", None)
    assert not result.ok
    assert "语法" in result.chinese
    assert "Parser Error" in result.raw_error or "syntax error" in result.raw_error.lower()
    missing = execute_student_sql(con, "SELECT * FROM dwd_trade_order_item", None)
    assert not missing.ok
    assert "dwd_trade_order_item" in missing.chinese
    allowed, message = guard_sql("DROP TABLE ods_order")
    assert not allowed
    assert "不能删除" in message
    blocked = execute_student_sql(con, "SELECT * FROM read_csv_auto('/etc/passwd')", None)
    assert not blocked.ok
    con.close()


def test_dashboard_changes_after_sql_rerun():
    con = _new_db()
    _run_reference_chain(con)
    daily, _ = read_daily(con)
    assert float(daily["pay_amt"].sum()) == 1760
    con.execute(
        """
        CREATE OR REPLACE TABLE ads_ops_daily AS
        SELECT
            DATE '2026-03-01' AS stat_date,
            '星期日' AS weekday_name,
            1 AS order_cnt,
            1 AS order_amt,
            999 AS pay_amt,
            0 AS refund_amt,
            999 AS net_pay_amt
        """
    )
    changed, message = read_daily(con)
    assert message == ""
    assert float(changed["pay_amt"].sum()) == 999
    con.close()


def test_lineage_matches_reference_sql():
    answers = {question.id: question.answer for question in QUESTIONS}
    passed, messages = grade_lineage(answers)
    assert passed, messages
    wrong = dict(answers)
    wrong["ods_field"] = "item_amount_yuan"
    wrong["date_rule"] = "下单日期 order_date"
    passed, messages = grade_lineage(wrong)
    assert not passed
    assert "ODS" in messages[0] or "源表" in messages[0] or "不一致" in messages[0]

    pay_sql = get_exercise("e04_dwd_pay").reference_sql
    user_sql = get_exercise("e07_dws_user").reference_sql
    daily_sql = get_exercise("e10_ads_daily").reference_sql
    assert "dws_user_1d" in daily_sql
    assert "pay_amt" in daily_sql
    assert "dws_shop_1d" not in daily_sql
    assert "pay_date" in user_sql
    assert "支付成功" in user_sql
    assert "pay_amount_fen / 100.0" in pay_sql
    assert "ods_payment" in pay_sql


def test_reset_restores_seed():
    con = _new_db()
    con.execute("CREATE TABLE dwd_trade_payment AS SELECT 1 AS payment_id")
    reset_database(con)
    assert con.execute("SELECT COUNT(*) FROM ods_order").fetchone()[0] == 8
    gone = con.execute(
        """
        SELECT COUNT(*) FROM information_schema.tables
        WHERE table_schema = 'main' AND table_name = 'dwd_trade_payment'
        """
    ).fetchone()[0]
    assert gone == 0
    con.close()


def test_explain_group_by():
    text = explain_error(
        'Binder Error: column "item_amount" must appear in the GROUP BY clause or must be part of an aggregate function.'
    )
    assert "GROUP BY" in text
