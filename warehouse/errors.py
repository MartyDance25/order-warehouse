"""把 DuckDB 报错翻成短的中文说明。原始报错仍会一并展示。"""

from __future__ import annotations

import re

_TABLE_HINTS = {
    "dwd_trade_order_item": "还没有订单商品明细 dwd_trade_order_item。请先完成「订单商品明细」并提交通过。",
    "dwd_trade_payment": "还没有支付明细 dwd_trade_payment。请先完成「支付明细」并提交通过。",
    "dwd_trade_refund": "还没有退款明细 dwd_trade_refund。请先完成「退款明细」并提交通过。",
    "dws_user_1d": "还没有用户日汇总 dws_user_1d。请先完成「用户日汇总」。运营日报的参考路径读取的是这张表。",
    "dws_sku_1d": "还没有商品日汇总 dws_sku_1d。请先完成「商品日汇总」。",
    "dws_shop_1d": "还没有店铺日汇总 dws_shop_1d。请先完成「店铺日汇总」。",
    "dim_sku": "找不到商品维表 dim_sku。可以点「重置模拟数据」恢复维度表。",
    "dim_date": "找不到日期维表 dim_date。可以点「重置模拟数据」恢复。",
    "ods_order": "找不到订单主表 ods_order。可以点「重置模拟数据」恢复贴源表。",
    "ods_order_item": "找不到订单商品明细 ods_order_item。可以点「重置模拟数据」恢复贴源表。",
    "ods_payment": "找不到支付表 ods_payment。可以点「重置模拟数据」恢复贴源表。",
    "ods_refund": "找不到退款表 ods_refund。可以点「重置模拟数据」恢复贴源表。",
}


def explain_error(raw: str) -> str:
    text = raw.lower()
    if "maximum execution time" in text or "interrupt error" in text:
        return "查询超时了。多半是 JOIN 条件漏了，两张表被乘成了笛卡尔积。请检查关联字段。"
    if "file system operations are disabled" in text or "permission error" in text:
        return "不能访问数据库以外的文件。请只查询实训台里的表。"
    if "configuration has been locked" in text or "cannot change configuration" in text or "cannot enable external access" in text:
        return "不能修改数据库配置，也不能打开外部文件访问。请只编写查询或建表语句。"
    if "parser error" in text or "syntax error" in text:
        return "这是语法错误。请检查关键字是否写全、括号是否成对、逗号是否多了或少了。"
    if "must appear in the group by" in text:
        return "聚合不完整。没有放进聚合函数的字段，需要写到 GROUP BY 里。"
    if "ambiguous" in text:
        return "有字段在多张表里重名了。请加上表别名，例如 o.order_id、i.sku_code。"
    if "referenced column" in text or "not found in from clause" in text:
        return "找不到这个字段。请到左侧表目录核对字段名，注意下划线。"
    if "does not exist" in text or "not found" in text:
        for name, hint in _TABLE_HINTS.items():
            if name in text:
                return hint
        found = re.search(r"table with name ([a-z0-9_]+)", text)
        if found:
            return f"找不到表 {found.group(1)}。请核对表名，或先完成上一层练习，把这张表生成出来。"
        return "找不到表或字段。请核对名称，或先完成依赖的上一道练习。"
    if "conversion" in text or "could not convert" in text or "type mismatch" in text:
        return "字段类型对不上。金额请先按数值除以 100，日期不要和普通数字直接比较。"
    return "执行没有成功。请根据下面的数据库原始报错检查表名、字段名和语法。"
