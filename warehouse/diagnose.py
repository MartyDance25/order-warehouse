"""根据结果差异写出具体口径提示。只看结果，不看 SQL 文本。"""

from __future__ import annotations

import math
from datetime import date, datetime
from decimal import Decimal

import pandas as pd

from warehouse.exercises import Exercise

LABELS = {
    "order_id": "订单",
    "order_item_id": "商品行",
    "payment_id": "支付编号",
    "refund_id": "退款编号",
    "user_id": "用户",
    "shop_id": "店铺",
    "sku_id": "SKU",
    "sku_code": "SKU 编码",
    "stat_date": "日期",
    "rank_no": "名次",
    "pay_amt": "实付金额",
    "pay_amount_yuan": "实付金额",
    "refund_amt": "退款金额",
    "refund_amount_yuan": "退款金额",
    "order_amt": "下单商品金额",
    "order_cnt": "订单数",
    "sale_amt": "商品销售额",
    "sale_qty": "销售件数",
    "item_amount_yuan": "商品明细金额",
    "net_pay_amt": "净额",
    "pay_status_name": "支付状态",
    "refund_status_name": "退款状态",
    "order_status_name": "订单状态",
    "sku_name": "商品名称",
    "category_name": "品类",
    "weekday_name": "星期",
}


def is_null(value) -> bool:
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except TypeError:
        return False


def show(value) -> str:
    if is_null(value):
        return "空值"
    if isinstance(value, pd.Timestamp):
        value = value.to_pydatetime()
    if isinstance(value, datetime):
        if value.hour == value.minute == value.second == 0:
            return value.date().isoformat()
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        value = float(value)
    if isinstance(value, float):
        if math.isnan(value):
            return "空值"
        if abs(value - round(value)) < 1e-6:
            return str(int(round(value)))
        return f"{value:.2f}"
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    return str(value).strip()


def as_number(value) -> float | None:
    if is_null(value):
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float, Decimal)):
        number = float(value)
        if math.isnan(number):
            return None
        return number
    text = str(value).strip().replace(",", "")
    try:
        return float(text)
    except ValueError:
        return None


def _lower_frame(frame: pd.DataFrame | None) -> pd.DataFrame:
    if frame is None:
        return pd.DataFrame()
    out = frame.copy()
    out.columns = [str(name).lower() for name in out.columns]
    return out


def _records(frame: pd.DataFrame) -> list[dict]:
    if frame.empty:
        return []
    return frame.to_dict("records")


def _sum_by(frame: pd.DataFrame, key: str, value: str) -> dict[str, float]:
    totals: dict[str, float] = {}
    if key not in frame.columns or value not in frame.columns:
        return totals
    for row in _records(frame):
        amount = as_number(row.get(value))
        if amount is None:
            continue
        totals[show(row.get(key))] = totals.get(show(row.get(key)), 0.0) + amount
    return totals


def _close(left: float | None, right: float) -> bool:
    return left is not None and abs(left - right) < 0.02


def diagnose(exercise: Exercise, student: pd.DataFrame | None, expected: pd.DataFrame | None) -> list[str]:
    handler = _HANDLERS.get(exercise.id)
    if handler is None:
        return []
    return handler(_lower_frame(student), _lower_frame(expected))


def _pay_unit_and_status(student: pd.DataFrame, expected: pd.DataFrame, amount_col: str, status_col: str, id_col: str, focus_id: str) -> list[str]:
    messages: list[str] = []
    if amount_col in student.columns and id_col in student.columns:
        got = _sum_by(student, id_col, amount_col).get(focus_id)
        exp = _sum_by(expected, id_col, amount_col).get(focus_id)
        if exp is not None and _close(got, exp * 100):
            messages.append(
                f"预期是 {show(exp)} 元，你算出了 {show(got)}。源字段的单位是分，100 分等于 1 元，请除以 100。"
            )
    if status_col in student.columns and amount_col in student.columns:
        for row in _records(student):
            status = show(row.get(status_col))
            if status in {"1", "2", "3", "4", "1.0", "2.0", "3.0", "4.0"}:
                if status_col == "refund_status_name":
                    messages.append(
                        f"退款状态还是编码 {status}。请译成中文：1 申请中，2 退款成功，3 退款驳回。"
                    )
                else:
                    messages.append(
                        f"支付状态还是编码 {status}。请译成中文：1 待支付，2 支付成功，3 支付失败，4 已关闭。"
                    )
                break
    return messages


def _diagnose_payment(student: pd.DataFrame, expected: pd.DataFrame) -> list[str]:
    return _pay_unit_and_status(student, expected, "pay_amount_yuan", "pay_status_name", "payment_id", "P1001")


def _diagnose_refund(student: pd.DataFrame, expected: pd.DataFrame) -> list[str]:
    messages = _pay_unit_and_status(
        student, expected, "refund_amount_yuan", "refund_status_name", "refund_id", "R1001"
    )
    if "refund_id" in student.columns:
        ids = {show(row.get("refund_id")) for row in _records(student)}
        expected_ids = {show(row.get("refund_id")) for row in _records(expected)} if "refund_id" in expected.columns else set()
        if "R1007" in expected_ids and "R1007" not in ids:
            messages.append("退款明细要保留申请中的记录。R1007 还在申请中，编码 1，不应删掉。成功与否留到汇总层再筛选。")
    return messages


def _diagnose_dup(student: pd.DataFrame, expected: pd.DataFrame) -> list[str]:
    messages: list[str] = []
    if "order_id" not in student.columns or "pay_amount_yuan" not in student.columns:
        return messages
    got = _sum_by(student, "order_id", "pay_amount_yuan")
    exp = _sum_by(expected, "order_id", "pay_amount_yuan")
    if _close(got.get("O1001"), 800) and _close(exp.get("O1001"), 400):
        messages.append("预期实付 400 元，你算出了 800 元。检查 JOIN 后同一支付编号出现了几次。O1001 只有一笔支付 P1001。")
    elif _close(got.get("O1001"), 40000):
        messages.append("预期实付 400 元，你算出了 40000。这是分。40000 分等于 400 元，请除以 100。")
    for order_id, expected_amount in exp.items():
        actual = got.get(order_id)
        if order_id == "O1001":
            continue
        if actual is not None and _close(actual, expected_amount * 2) and expected_amount > 0:
            messages.append(
                f"订单 {order_id} 的实付预期 {show(expected_amount)} 元，你算出了 {show(actual)} 元。这张订单有多条商品明细，整单支付被重复加总了。"
            )
    if "payment_id" in student.columns:
        counts: dict[str, int] = {}
        for row in _records(student):
            payment_id = show(row.get("payment_id"))
            counts[payment_id] = counts.get(payment_id, 0) + 1
        repeated = [payment_id for payment_id, count in counts.items() if count > 1 and payment_id != "空值"]
        if repeated and not any("800" in message for message in messages):
            messages.append(
                "支付编号 " + "、".join(repeated[:3]) + " 出现了多次。支付金额是整单一行，不能按商品行各记一次。"
            )
    present = set(got)
    if "O1002" in present:
        messages.append("订单 O1002 还是待支付，80 元不能算实付。请只保留支付状态编码 2。")
    if "O1005" in present:
        messages.append("订单 O1005 支付失败，不能算实付。")
    return messages


def _lookup(frame: pd.DataFrame, columns: tuple[str, ...], values: tuple[str, ...], metric: str):
    if any(column not in frame.columns for column in columns) or metric not in frame.columns:
        return None
    for row in _records(frame):
        if tuple(show(row.get(column)) for column in columns) == values:
            return row.get(metric)
    return None


def _diagnose_user(student: pd.DataFrame, expected: pd.DataFrame) -> list[str]:
    messages: list[str] = []
    keys = ("stat_date", "user_id")
    refund_on_order_day = _lookup(student, keys, ("2026-03-01", "U001"), "refund_amt")
    refund_on_refund_day = _lookup(student, keys, ("2026-03-03", "U001"), "refund_amt")
    expected_refund_day = _lookup(expected, keys, ("2026-03-03", "U001"), "refund_amt")
    if _close(as_number(refund_on_order_day), 100) and not _close(as_number(refund_on_refund_day), 100) and _close(as_number(expected_refund_day), 100):
        messages.append("退款应按退款日期归集。U001 的 100 元是 2026-03-03 退的球鞋，不应算进 2026-03-01 的下单日。")
    pay_u002 = _lookup(student, keys, ("2026-03-01", "U002"), "pay_amt")
    if _close(as_number(pay_u002), 680):
        messages.append("U002 在 2026-03-01 的实付预期 600 元，你算出了 680 元。O1002 的 80 元还是待支付，不能加进实付。")
    pay_u004 = _lookup(student, keys, ("2026-03-05", "U004"), "pay_amt")
    if _close(as_number(pay_u004), 100):
        messages.append("U004 在 2026-03-05 的支付失败了，实付应为 0，不应把 100 元算进去。")
    orders_u002 = _lookup(student, keys, ("2026-03-01", "U002"), "order_cnt")
    if _close(as_number(orders_u002), 1):
        messages.append("2026-03-01 用户 U002 有 O1002 和 O1006 两笔订单。订单数要按不同订单号计数，结果应是 2。")
    if _lookup(student, keys, ("2026-03-03", "U001"), "user_id") is None and _close(as_number(expected_refund_day), 100):
        messages.append("缺少用户 U001 在 2026-03-03 的行。这一天没有新订单，但有 100 元成功退款，汇总行要保留。")
    return messages


def _diagnose_sku(student: pd.DataFrame, expected: pd.DataFrame) -> list[str]:
    messages: list[str] = []
    keys = ("stat_date", "sku_id")
    shoe = "SKU102"
    cup = "SKU201"
    sale = _lookup(student, keys, ("2026-03-04", cup), "sale_amt")
    refund = _lookup(student, keys, ("2026-03-04", cup), "refund_amt")
    if _close(as_number(sale), 80):
        messages.append("2026-03-04 运动水杯的商品销售额预期 120 元，你算出了 80 元。商品销售额先采用商品明细金额，不要把当天 40 元退款减掉。退款记在 refund_amt。")
    shoe_refund_day = _lookup(student, keys, ("2026-03-03", shoe), "refund_amt")
    shoe_sale_day = _lookup(student, keys, ("2026-03-01", shoe), "refund_amt")
    if _lookup(student, keys, ("2026-03-03", shoe), "sku_id") is None:
        messages.append("缺少 2026-03-03 的羽毛球鞋。这一天没有新下单，但 O1001 的 100 元退款发生在这一天，sale_amt 为 0，refund_amt 为 100。")
    elif _close(as_number(shoe_sale_day), 100) and not _close(as_number(shoe_refund_day), 100):
        messages.append("球鞋 100 元退款发生在 2026-03-03，不是下单日 2026-03-01。")
    if refund is not None and as_number(refund) == 0 and _close(as_number(sale), 120):
        messages.append("2026-03-04 运动水杯有 40 元成功退款。退款按退款日期记到 refund_amt，不要留成 0。")
    return messages


def _diagnose_shop(student: pd.DataFrame, expected: pd.DataFrame) -> list[str]:
    messages: list[str] = []
    keys = ("stat_date", "shop_id")
    if _lookup(student, keys, ("2026-03-03", "S001"), "shop_id") is None:
        messages.append("缺少店铺 S001 在 2026-03-03 的行。羽动体育这一天没有新订单，但有 100 元成功退款。")
    refund = _lookup(student, keys, ("2026-03-01", "S001"), "refund_amt")
    if _close(as_number(refund), 100):
        messages.append("S001 的 100 元退款应按退款日期记到 2026-03-03，不应记在 2026-03-01。")
    pay = _lookup(student, keys, ("2026-03-01", "S001"), "pay_amt")
    if _close(as_number(pay), 400):
        messages.append("S001 在 2026-03-01 的实付预期 1000 元，你算出了 400 元。当天还有 O1006 支付成功的 600 元。")
    return messages


def _diagnose_daily(student: pd.DataFrame, expected: pd.DataFrame) -> list[str]:
    messages: list[str] = []
    if "stat_date" not in student.columns:
        return messages
    for row in _records(expected):
        day = show(row.get("stat_date"))
        got_pay = _lookup(student, ("stat_date",), (day,), "pay_amt")
        exp_pay = as_number(row.get("pay_amt"))
        exp_order = as_number(row.get("order_amt"))
        got_pay_num = as_number(got_pay)
        if exp_pay is not None and exp_order is not None and abs(exp_pay - exp_order) > 0.02 and _close(got_pay_num, exp_order):
            messages.append(
                f"{day} 的实付金额预期 {show(exp_pay)} 元，你算出了 {show(got_pay_num)} 元。这个数和下单商品金额一样，未支付成功的金额被算进实付了。"
            )
        got_refund = as_number(_lookup(student, ("stat_date",), (day,), "refund_amt"))
        exp_refund = as_number(row.get("refund_amt"))
        if day == "2026-03-03" and _close(exp_refund, 100) and (got_refund is None or _close(got_refund, 0)):
            messages.append("2026-03-03 的退款金额预期 100 元。这是 O1001 的球鞋退款，退款日期是 3 月 3 日，不是下单日 3 月 1 日。")
        got_net = as_number(_lookup(student, ("stat_date",), (day,), "net_pay_amt"))
        exp_net = as_number(row.get("net_pay_amt"))
        if day == "2026-03-03" and _close(exp_net, 50) and _close(got_net, 150):
            messages.append("2026-03-03 的净额预期 50 元，等于当天实付 150 减当天退款 100。净额是同一天的两个指标相减。")
    if "weekday_name" not in student.columns:
        messages.append("请用 dim_date.date_day 关联 stat_date，补上 weekday_name。2026-03-01 是星期日。")
    return messages


def _diagnose_rank(student: pd.DataFrame, expected: pd.DataFrame) -> list[str]:
    messages: list[str] = []
    if "sku_id" not in student.columns or "stat_date" not in student.columns:
        return messages
    keys = ("stat_date", "sku_id")
    if _lookup(student, keys, ("2026-03-03", "SKU102"), "sku_id") is not None:
        sale = as_number(_lookup(student, keys, ("2026-03-03", "SKU102"), "sale_amt"))
        if sale is None or _close(sale, 0):
            messages.append("3 月 3 日的羽毛球鞋只有退款、没有销售额，不应进入排行榜。请保留 sale_amt 大于 0 的商品。")
    top_amt = _lookup(student, keys, ("2026-03-01", "SKU101"), "sale_amt")
    top_rank = _lookup(student, keys, ("2026-03-01", "SKU101"), "rank_no")
    if top_amt is not None and not _close(as_number(top_amt), 900):
        messages.append(f"2026-03-01 羽毛球拍的商品销售额预期 900 元，你算出了 {show(top_amt)} 元。排行用的是商品明细金额，球拍当天是 300 加 600。")
    if top_rank is not None and not _close(as_number(top_rank), 1) and _close(as_number(top_amt), 900):
        messages.append("2026-03-01 羽毛球拍的销售额是 900 元，名次应为 1。请按 sale_amt 从高到低编号。")
    return messages


_HANDLERS = {
    "e04_dwd_pay": _diagnose_payment,
    "e05_dwd_refund": _diagnose_refund,
    "e06_pay_dup": _diagnose_dup,
    "e07_dws_user": _diagnose_user,
    "e08_dws_sku": _diagnose_sku,
    "e09_dws_shop": _diagnose_shop,
    "e10_ads_daily": _diagnose_daily,
    "e11_ads_rank": _diagnose_rank,
}
