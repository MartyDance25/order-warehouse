"""实付金额的参考血缘。答案和运营日报、用户日汇总、支付明细的参考 SQL 是同一条路径。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LineageQuestion:
    id: str
    prompt: str
    options: tuple[str, ...]
    answer: str


QUESTIONS: tuple[LineageQuestion, ...] = (
    LineageQuestion(
        "ads_table",
        "运营日报里的实付金额，在哪张 ADS 表？",
        ("ads_ops_daily", "ads_sku_rank_1d", "dws_user_1d", "ods_payment"),
        "ads_ops_daily",
    ),
    LineageQuestion(
        "ads_field",
        "这张 ADS 表的哪个字段是实付金额？",
        ("pay_amt", "order_amt", "refund_amt", "net_pay_amt", "sale_amt"),
        "pay_amt",
    ),
    LineageQuestion(
        "dws_table",
        "参考 SQL 从哪张 DWS 表把实付金额汇上来？店铺日汇总加总也能得到同一个数，但参考实现不走那条路径。",
        ("dws_user_1d", "dws_shop_1d", "dws_sku_1d", "dwd_trade_payment"),
        "dws_user_1d",
    ),
    LineageQuestion(
        "dws_field",
        "用的是这张 DWS 表的哪个字段？",
        ("pay_amt", "order_amt", "refund_amt", "sale_amt"),
        "pay_amt",
    ),
    LineageQuestion(
        "dwd_table",
        "这个 DWS 字段来自哪张 DWD 明细表？",
        ("dwd_trade_payment", "dwd_trade_order_item", "dwd_trade_refund", "ods_order"),
        "dwd_trade_payment",
    ),
    LineageQuestion(
        "dwd_field",
        "DWD 上对应的金额字段叫什么？",
        ("pay_amount_yuan", "pay_amount_fen", "item_amount_yuan", "refund_amount_yuan"),
        "pay_amount_yuan",
    ),
    LineageQuestion(
        "ods_table",
        "金额最早来自哪张 ODS 源表？",
        ("ods_payment", "ods_order", "ods_order_item", "ods_refund"),
        "ods_payment",
    ),
    LineageQuestion(
        "ods_field",
        "源表上的哪个字段？",
        ("pay_amount_fen", "item_amount_yuan", "pay_amount_yuan", "refund_amount_fen"),
        "pay_amount_fen",
    ),
    LineageQuestion(
        "unit_rule",
        "金额中间做了什么转换？",
        (
            "DWD 把 ods_payment.pay_amount_fen 除以 100，得到 pay_amount_yuan",
            "ADS 再次把金额除以 100",
            "贴源金额已经是元，全程不转换",
            "把商品明细金额乘以 100 当成实付",
        ),
        "DWD 把 ods_payment.pay_amount_fen 除以 100，得到 pay_amount_yuan",
    ),
    LineageQuestion(
        "status_rule",
        "状态在哪一层筛选？",
        (
            "DWD 保留全部支付并把编码译成中文；DWS 只汇总支付成功（编码 2）",
            "DWD 直接删掉待支付和支付失败",
            "不过滤状态，所有支付金额都加进去",
            "只保留退款成功的记录",
        ),
        "DWD 保留全部支付并把编码译成中文；DWS 只汇总支付成功（编码 2）",
    ),
    LineageQuestion(
        "date_rule",
        "实付金额按哪一天归集？",
        ("支付日期 pay_date", "下单日期 order_date", "退款日期 refund_date", "用户注册日期"),
        "支付日期 pay_date",
    ),
    LineageQuestion(
        "dws_agg",
        "DWS 层怎么汇总实付？",
        (
            "按 user_id 和 pay_date，对支付成功的 pay_amount_yuan 求和",
            "按 user_id 和下单日期，对商品明细金额求和",
            "按 sku_code 和下单日期，对商品明细金额求和",
            "先把支付表 JOIN 到商品明细，再把支付金额求和",
        ),
        "按 user_id 和 pay_date，对支付成功的 pay_amount_yuan 求和",
    ),
    LineageQuestion(
        "ads_agg",
        "ADS 层怎么得到日报上的实付金额？",
        (
            "按 stat_date 对 dws_user_1d.pay_amt 再求和",
            "按 stat_date 对商品销售额做排名",
            "直接取订单主表的 item_amount_yuan",
            "按店铺取实付最大的那一行",
        ),
        "按 stat_date 对 dws_user_1d.pay_amt 再求和",
    ),
)


REFERENCE_STEPS: tuple[tuple[str, str], ...] = (
    (
        "ADS 运营日报",
        "ads_ops_daily.pay_amt。按 stat_date 对 dws_user_1d.pay_amt 求和，并关联 dim_date 补上星期。",
    ),
    (
        "DWS 用户日汇总",
        "dws_user_1d.pay_amt。只保留 dwd_trade_payment 里 pay_status_name = '支付成功' 的记录，按 user_id + pay_date 对 pay_amount_yuan 求和。",
    ),
    (
        "DWD 支付明细",
        "dwd_trade_payment.pay_amount_yuan = ods_payment.pay_amount_fen / 100。pay_status_code 译成中文，这一层不删除失败或待支付记录。user_id、shop_id 来自 ods_order，金额本身不来自订单主表。",
    ),
    (
        "ODS 支付表",
        "ods_payment.pay_amount_fen，单位是分。筛选条件落到源上是 pay_status_code = 2。日期用 pay_date，不是 order_date。",
    ),
)


def grade_lineage(answers: dict[str, str]) -> tuple[bool, list[str]]:
    wrong = []
    for question in QUESTIONS:
        got = (answers.get(question.id) or "").strip()
        if got != question.answer:
            wrong.append(question.prompt)
    if not wrong:
        return True, ["这条血缘和参考 SQL 一致。"]
    preview = "；".join(wrong[:4])
    extra = "" if len(wrong) <= 4 else f" 等 {len(wrong)} 处"
    return False, [f"还有 {len(wrong)} 处和参考链路不一致：{preview}{extra}。"]
