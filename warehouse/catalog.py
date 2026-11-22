"""贴源表、维度表的粒度说明和字段字典。"""

from __future__ import annotations

TABLES: dict[str, dict] = {
    "ods_order": {
        "layer": "ODS 贴源层",
        "title": "订单主表",
        "grain": "一行代表一笔订单（一个订单号），不是一件商品，也不是一次支付。",
        "columns": [
            ("order_id", "VARCHAR", "订单号"),
            ("user_id", "VARCHAR", "下单用户编号"),
            ("shop_id", "VARCHAR", "店铺编号"),
            ("order_time", "TIMESTAMP", "下单时间"),
            ("order_date", "DATE", "下单日期。下单订单数、下单商品金额按这个日期归集"),
            ("order_status_code", "INTEGER", "订单状态编码：10 待支付，20 已支付，30 部分退款"),
            (
                "item_amount_yuan",
                "DECIMAL(18,2)",
                "订单商品金额合计（元），等于该订单全部商品明细金额之和。未支付的订单也有这个金额。它不是实付金额",
            ),
        ],
    },
    "ods_order_item": {
        "layer": "ODS 贴源层",
        "title": "订单商品明细表",
        "grain": "一行代表订单中的一个商品行。订单 O1001 有两行：球拍 300 元、球鞋 100 元。",
        "columns": [
            ("order_item_id", "VARCHAR", "商品行号"),
            ("order_id", "VARCHAR", "所属订单号"),
            ("sku_code", "VARCHAR", "SKU 编码。关联商品维表时用这个字段，对 dim_sku.sku_code"),
            ("quantity", "INTEGER", "件数"),
            (
                "item_amount_yuan",
                "DECIMAL(18,2)",
                "该商品行金额（元），已按单价乘以件数算好。这就是「商品明细金额」，不是整单支付金额",
            ),
        ],
    },
    "ods_payment": {
        "layer": "ODS 贴源层",
        "title": "支付表",
        "grain": "一行代表一次支付尝试。金额覆盖整单，不是按商品行拆开的。一笔订单在本题只有一条支付记录。",
        "columns": [
            ("payment_id", "VARCHAR", "支付编号"),
            ("order_id", "VARCHAR", "订单号"),
            ("pay_time", "TIMESTAMP", "支付时间"),
            ("pay_date", "DATE", "支付日期。实付金额按这个日期归集，不按下单日期"),
            (
                "pay_amount_fen",
                "BIGINT",
                "支付金额，单位是分。100 分 = 1 元。O1001 这里是 40000，表示 400 元",
            ),
            (
                "pay_status_code",
                "INTEGER",
                "支付状态编码：1 待支付，2 支付成功，3 支付失败，4 已关闭。只有 2 计入实付",
            ),
        ],
    },
    "ods_refund": {
        "layer": "ODS 贴源层",
        "title": "退款表",
        "grain": "一行代表一次退款申请，退到具体商品行。只有退款成功的金额才进入实退。",
        "columns": [
            ("refund_id", "VARCHAR", "退款编号"),
            ("order_id", "VARCHAR", "订单号"),
            ("order_item_id", "VARCHAR", "退的是哪一个商品行"),
            ("refund_time", "TIMESTAMP", "退款时间"),
            ("refund_date", "DATE", "退款日期。退款金额按这个日期归集，不按下单日期，也不按支付日期"),
            ("refund_amount_fen", "BIGINT", "退款金额，单位是分。100 分 = 1 元"),
            (
                "refund_status_code",
                "INTEGER",
                "退款状态编码：1 申请中，2 退款成功，3 退款驳回。只有 2 计入退款金额",
            ),
        ],
    },
    "dim_user": {
        "layer": "DIM 维度层",
        "title": "用户维表",
        "grain": "一行代表一个用户。",
        "columns": [
            ("user_id", "VARCHAR", "用户编号"),
            ("user_name", "VARCHAR", "用户姓名"),
            ("city", "VARCHAR", "所在城市"),
            ("register_date", "DATE", "注册日期"),
        ],
    },
    "dim_shop": {
        "layer": "DIM 维度层",
        "title": "店铺维表",
        "grain": "一行代表一个店铺。",
        "columns": [
            ("shop_id", "VARCHAR", "店铺编号"),
            ("shop_name", "VARCHAR", "店铺名称"),
            ("shop_type", "VARCHAR", "店铺类型，例如自营、专营"),
        ],
    },
    "dim_sku": {
        "layer": "DIM 维度层",
        "title": "商品 SKU 维表",
        "grain": "一行代表一个可售卖的商品 SKU。订单明细用 SKU 编码来关联这张表。",
        "columns": [
            ("sku_id", "VARCHAR", "SKU 主键"),
            ("sku_code", "VARCHAR", "SKU 编码，关联键"),
            ("sku_name", "VARCHAR", "商品名称"),
            ("category_name", "VARCHAR", "品类名称"),
            ("shop_id", "VARCHAR", "商品所属店铺"),
            ("list_price_yuan", "DECIMAL(18,2)", "标价（元）"),
        ],
    },
    "dim_date": {
        "layer": "DIM 维度层",
        "title": "日期维表",
        "grain": "一行代表一个自然日。2026-03-01 是星期日。",
        "columns": [
            ("date_day", "DATE", "自然日"),
            ("year_num", "INTEGER", "年"),
            ("month_num", "INTEGER", "月"),
            ("day_num", "INTEGER", "日"),
            ("weekday_name", "VARCHAR", "星期，例如星期日"),
            ("is_weekend", "BOOLEAN", "是否周末"),
        ],
    },
}

SOURCE_TABLES = list(TABLES)
LAYER_ORDER = ["ODS 贴源层", "DIM 维度层", "我的结果表"]
