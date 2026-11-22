"""十二道练习。参考 SQL 同时被用来生成标准结果。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Exercise:
    id: str
    layer: str
    layer_name: str
    nav: str
    title: str
    goal: str
    prompt: str
    caliber: str
    target_table: str
    columns: tuple[tuple[str, str], ...]
    starter_sql: str
    reference_sql: str
    hints: tuple[str, ...]
    keys: tuple[str, ...]
    order_sensitive: bool = False
    mappings: tuple[tuple[str, str, str], ...] = ()
    deps: tuple[str, ...] = ()
    ref_deps: tuple[str, ...] = ()
    kind: str = "sql"
    bad_sql: str = ""
    bad_note: str = ""
    grain: str = ""


ORDER_GUIDE = """
| 订单 | 用户 | 店铺 | 下单日 | 商品明细 | 支付 | 退款 |
| --- | --- | --- | --- | --- | --- | --- |
| O1001 | 张伟 U001 | 羽动 S001 | 03-01 | 球拍 300 + 球鞋 100 | 03-01 成功 400 元（40000 分） | 03-03 球鞋成功 100 元 |
| O1002 | 李娜 U002 | 跑步店 S002 | 03-01 | 水杯 80 | 03-01 待支付 80 元，不算实付 | 无 |
| O1003 | 王磊 U003 | 羽动 S001 | 03-02 | 球拍 300 | 03-02 成功 300 元 | 无 |
| O1004 | 张伟 U001 | 跑步店 S002 | 03-02 | 短裤 150 + 水杯 40 | 03-02 成功 190 元 | 03-04 水杯成功 40 元 |
| O1005 | 陈静 U004 | 羽动 S001 | 03-05 | 球鞋 100 | 03-05 支付失败，不算实付 | 无 |
| O1006 | 李娜 U002 | 羽动 S001 | 03-01 | 球拍 600（2 件） | 03-01 成功 600 元 | 无 |
| O1007 | 王磊 U003 | 跑步店 S002 | 03-03 | 短裤 150 | 03-03 成功 150 元 | 03-03 申请中 150 元，不算实退 |
| O1008 | 陈静 U004 | 跑步店 S002 | 03-04 | 水杯 120（3 件） | 03-04 成功 120 元 | 无 |
""".strip()


EXERCISES: tuple[Exercise, ...] = (
    Exercise(
        id="e01_ods_order",
        layer="ODS",
        layer_name="ODS 贴源层",
        nav="认识订单主表",
        title="认识订单主表",
        goal="确认贴源订单主表的粒度：一行是一笔订单。先在左侧打开四张 ODS 表，看字段说明和样例。",
        prompt="""
先看左侧表目录里的四张贴源表。每张表都写了一行代表什么。

然后查询 `ods_order`，输出下面这些字段。不要关联商品明细，也不要把一行订单拆开。

O1001 的 `item_amount_yuan` 应为 400。这是球拍 300 元加球鞋 100 元，单位已经是元。支付表里的 40000 是分，不要在这道题里使用。
""".strip(),
        caliber="本表只看订单主表。订单数如果在这里数，一行就是一笔订单。商品行要去 ods_order_item。",
        target_table="wrk_ods_order_list",
        columns=(
            ("order_id", "订单号"),
            ("user_id", "用户编号"),
            ("shop_id", "店铺编号"),
            ("order_date", "下单日期"),
            ("order_status_code", "订单状态编码"),
            ("item_amount_yuan", "订单商品金额合计（元）"),
        ),
        starter_sql="""
SELECT
    order_id,
    user_id,
    shop_id,
    order_date,
    order_status_code,
    item_amount_yuan
FROM ods_order
""".strip(),
        reference_sql="""
CREATE OR REPLACE TABLE wrk_ods_order_list AS
SELECT
    order_id,
    user_id,
    shop_id,
    order_date,
    order_status_code,
    item_amount_yuan
FROM ods_order
""".strip(),
        hints=(
            "直接查 ods_order。一行就是一笔订单，这道题不要 JOIN 明细。",
            "字段只要 order_id、user_id、shop_id、order_date、order_status_code、item_amount_yuan。",
            "O1001 的 item_amount_yuan 是 400，不是 40000。40000 在支付表里，单位是分。",
        ),
        keys=("order_id",),
        grain="一行代表一笔订单。",
    ),
    Exercise(
        id="e02_dim_sku",
        layer="DIM",
        layer_name="DIM 维度层",
        nav="SKU 编码补全",
        title="用 SKU 编码补上商品名称和品类",
        goal="订单明细上只有 SKU 编码。把它关联到商品维表，补出名称和品类。",
        prompt="""
`ods_order_item` 没有商品名称，也没有 `sku_id`，只有 `sku_code`。

请用 SKU 编码关联 `dim_sku`，生成 `wrk_item_sku`。O1001 的两行应分别补成「羽毛球拍 / 球拍」和「羽毛球鞋 / 球鞋」。

不要用商品名称做关联键，名称可能重复，编码才是这道题的键。
""".strip(),
        caliber="关联条件是 ods_order_item.sku_code = dim_sku.sku_code。金额和件数从明细原样带出。",
        target_table="wrk_item_sku",
        columns=(
            ("order_item_id", "商品行号"),
            ("order_id", "订单号"),
            ("sku_code", "SKU 编码"),
            ("sku_id", "来自维表的 SKU 主键"),
            ("sku_name", "商品名称"),
            ("category_name", "品类"),
            ("quantity", "件数"),
            ("item_amount_yuan", "商品明细金额（元）"),
        ),
        starter_sql="""
CREATE OR REPLACE TABLE wrk_item_sku AS
SELECT
    i.order_item_id,
    i.order_id,
    i.sku_code,
    i.quantity,
    i.item_amount_yuan
FROM ods_order_item AS i
""".strip(),
        reference_sql="""
CREATE OR REPLACE TABLE wrk_item_sku AS
SELECT
    i.order_item_id,
    i.order_id,
    i.sku_code,
    s.sku_id,
    s.sku_name,
    s.category_name,
    i.quantity,
    i.item_amount_yuan
FROM ods_order_item AS i
JOIN dim_sku AS s
    ON i.sku_code = s.sku_code
""".strip(),
        hints=(
            "明细表上没有 sku_id。FROM ods_order_item 之后，再 JOIN dim_sku。",
            "关联条件写 i.sku_code = s.sku_code。不要写商品名称。",
            "从维表取出 sku_id、sku_name、category_name。O1001 球拍的编码是 YJ-RACKET-01。",
        ),
        keys=("order_item_id",),
        mappings=(
            ("order_item_id", "ods_order_item.order_item_id", "原样"),
            ("order_id", "ods_order_item.order_id", "原样"),
            ("sku_code", "ods_order_item.sku_code", "关联键"),
            ("sku_id", "dim_sku.sku_id", "按 sku_code 关联后取得"),
            ("sku_name", "dim_sku.sku_name", "按 sku_code 关联后取得"),
            ("category_name", "dim_sku.category_name", "按 sku_code 关联后取得"),
            ("quantity", "ods_order_item.quantity", "原样"),
            ("item_amount_yuan", "ods_order_item.item_amount_yuan", "商品明细金额，原样"),
        ),
        grain="一行仍是一个商品行，只是补上了维表属性。",
    ),
    Exercise(
        id="e03_dwd_item",
        layer="DWD",
        layer_name="DWD 明细层",
        nav="订单商品明细",
        title="生成订单商品明细",
        goal="自己写 JOIN，把订单主表和商品明细合成 DWD，并补上商品名称、品类和订单状态中文。",
        prompt="""
生成 `dwd_trade_order_item`。一行仍然是一个商品行，但要能同时看到这行商品属于谁、哪家店、哪一天下的单。

请 JOIN `ods_order` 和 `ods_order_item`。商品名称和品类继续用 `sku_code` 关联 `dim_sku`。

订单状态请译成中文：10 待支付，20 已支付，30 部分退款。

金额用商品明细上的 `item_amount_yuan`。不要关联支付表，否则 O1001 的两行会被支付记录带偏。
""".strip(),
        caliber="粒度是商品行。用户、店铺、下单日期来自订单主表。商品属性来自维表。商品明细金额不转换成实付。",
        target_table="dwd_trade_order_item",
        columns=(
            ("order_item_id", "商品行号"),
            ("order_id", "订单号"),
            ("user_id", "用户编号，来自订单主表"),
            ("shop_id", "店铺编号，来自订单主表"),
            ("sku_id", "SKU 主键，来自维表"),
            ("sku_code", "SKU 编码"),
            ("sku_name", "商品名称"),
            ("category_name", "品类"),
            ("order_time", "下单时间"),
            ("order_date", "下单日期"),
            ("order_status_code", "订单状态编码"),
            ("order_status_name", "订单状态中文"),
            ("quantity", "件数"),
            ("item_amount_yuan", "商品明细金额（元）"),
        ),
        starter_sql="""
CREATE OR REPLACE TABLE dwd_trade_order_item AS
SELECT
    i.order_item_id,
    i.order_id,
    i.sku_code,
    i.quantity,
    i.item_amount_yuan
FROM ods_order_item AS i
""".strip(),
        reference_sql="""
CREATE OR REPLACE TABLE dwd_trade_order_item AS
SELECT
    i.order_item_id,
    i.order_id,
    o.user_id,
    o.shop_id,
    s.sku_id,
    i.sku_code,
    s.sku_name,
    s.category_name,
    o.order_time,
    o.order_date,
    o.order_status_code,
    CASE o.order_status_code
        WHEN 10 THEN '待支付'
        WHEN 20 THEN '已支付'
        WHEN 30 THEN '部分退款'
        ELSE '未知'
    END AS order_status_name,
    i.quantity,
    i.item_amount_yuan
FROM ods_order_item AS i
JOIN ods_order AS o
    ON i.order_id = o.order_id
JOIN dim_sku AS s
    ON i.sku_code = s.sku_code
""".strip(),
        hints=(
            "用 i.order_id = o.order_id 把商品明细连到订单主表，取出 user_id、shop_id、order_time、order_date、order_status_code。",
            "再用 i.sku_code = s.sku_code 连接 dim_sku，取出 sku_id、sku_name、category_name。",
            "CASE order_status_code：10 待支付，20 已支付，30 部分退款。O1001 应是两行，金额 300 和 100。",
        ),
        keys=("order_item_id",),
        mappings=(
            ("order_item_id", "ods_order_item.order_item_id", "原样"),
            ("order_id", "ods_order_item.order_id", "原样，也是连接订单主表的键"),
            ("user_id", "ods_order.user_id", "按 order_id 关联订单主表"),
            ("shop_id", "ods_order.shop_id", "按 order_id 关联订单主表"),
            ("sku_id", "dim_sku.sku_id", "按 sku_code 关联"),
            ("sku_code", "ods_order_item.sku_code", "原样"),
            ("sku_name", "dim_sku.sku_name", "按 sku_code 关联"),
            ("category_name", "dim_sku.category_name", "按 sku_code 关联"),
            ("order_time", "ods_order.order_time", "原样"),
            ("order_date", "ods_order.order_date", "下单日期"),
            ("order_status_code", "ods_order.order_status_code", "原样"),
            ("order_status_name", "ods_order.order_status_code", "10 待支付，20 已支付，30 部分退款"),
            ("quantity", "ods_order_item.quantity", "原样"),
            ("item_amount_yuan", "ods_order_item.item_amount_yuan", "商品明细金额（元），不要换成支付金额"),
        ),
        grain="一行代表一个订单商品行，已经带上订单和商品属性。",
    ),
    Exercise(
        id="e04_dwd_pay",
        layer="DWD",
        layer_name="DWD 明细层",
        nav="支付明细",
        title="生成支付明细",
        goal="把支付金额从分换成元，并把状态编码译成中文。这一层先不要删掉未成功的支付。",
        prompt="""
生成 `dwd_trade_payment`。一行仍是一次支付。

`pay_amount_fen` 的单位是分，目标字段 `pay_amount_yuan` 用元。O1001 的支付编号 P1001 应是 400 元，不是 40000。

状态编码：1 待支付，2 支付成功，3 支付失败，4 已关闭。

用户和店铺从 `ods_order` 取。待支付的 O1002、支付失败的 O1005 都要留在明细里，成功与否到汇总层再筛选。
""".strip(),
        caliber="DWD 做清洗：分转元、编码译成中文。不在这一层过滤支付状态。",
        target_table="dwd_trade_payment",
        columns=(
            ("payment_id", "支付编号"),
            ("order_id", "订单号"),
            ("user_id", "用户编号"),
            ("shop_id", "店铺编号"),
            ("pay_time", "支付时间"),
            ("pay_date", "支付日期"),
            ("pay_amount_fen", "支付金额（分）"),
            ("pay_amount_yuan", "支付金额（元）"),
            ("pay_status_code", "支付状态编码"),
            ("pay_status_name", "支付状态中文"),
        ),
        starter_sql="""
CREATE OR REPLACE TABLE dwd_trade_payment AS
SELECT
    p.payment_id,
    p.order_id,
    o.user_id,
    o.shop_id,
    p.pay_time,
    p.pay_date,
    p.pay_amount_fen,
    p.pay_amount_fen AS pay_amount_yuan,
    p.pay_status_code,
    CAST(p.pay_status_code AS VARCHAR) AS pay_status_name
FROM ods_payment AS p
JOIN ods_order AS o
    ON p.order_id = o.order_id
""".strip(),
        reference_sql="""
CREATE OR REPLACE TABLE dwd_trade_payment AS
SELECT
    p.payment_id,
    p.order_id,
    o.user_id,
    o.shop_id,
    p.pay_time,
    p.pay_date,
    p.pay_amount_fen,
    p.pay_amount_fen / 100.0 AS pay_amount_yuan,
    p.pay_status_code,
    CASE p.pay_status_code
        WHEN 1 THEN '待支付'
        WHEN 2 THEN '支付成功'
        WHEN 3 THEN '支付失败'
        WHEN 4 THEN '已关闭'
        ELSE '未知'
    END AS pay_status_name
FROM ods_payment AS p
JOIN ods_order AS o
    ON p.order_id = o.order_id
""".strip(),
        hints=(
            "P1001 的 pay_amount_fen 是 40000。pay_amount_yuan 写成 pay_amount_fen / 100.0，结果是 400。",
            "不要加 WHERE 删掉状态。O1002 的「待支付」和 O1005 的「支付失败」都该出现。",
            "用 CASE 把 1、2、3、4 译成待支付、支付成功、支付失败、已关闭。",
        ),
        keys=("payment_id",),
        mappings=(
            ("payment_id", "ods_payment.payment_id", "原样"),
            ("order_id", "ods_payment.order_id", "原样"),
            ("user_id", "ods_order.user_id", "按 order_id 关联，金额不来自订单主表"),
            ("shop_id", "ods_order.shop_id", "按 order_id 关联"),
            ("pay_time", "ods_payment.pay_time", "原样"),
            ("pay_date", "ods_payment.pay_date", "实付以后按这个日期汇总"),
            ("pay_amount_fen", "ods_payment.pay_amount_fen", "保留源字段，单位仍是分"),
            ("pay_amount_yuan", "ods_payment.pay_amount_fen", "除以 100，分转元"),
            ("pay_status_code", "ods_payment.pay_status_code", "原样保留"),
            ("pay_status_name", "ods_payment.pay_status_code", "1 待支付，2 支付成功，3 支付失败，4 已关闭"),
        ),
        grain="一行代表一次支付尝试，金额单位已经换成元。",
    ),
    Exercise(
        id="e05_dwd_refund",
        layer="DWD",
        layer_name="DWD 明细层",
        nav="退款明细",
        title="生成退款明细",
        goal="退款同样要处理分和状态编码，并保留尚未成功的申请。",
        prompt="""
生成 `dwd_trade_refund`。一行是一次退款申请。

金额从分换成元。O1001 的退款 R1001 是球鞋，应为 100 元，退款日期是 2026-03-03。

状态编码：1 申请中，2 退款成功，3 退款驳回。

请关联订单主表补 user_id、shop_id，关联商品明细补 sku_code。O1007 那笔 150 元还在申请中，要保留，不能删掉。
""".strip(),
        caliber="DWD 保留全部退款申请。只有「退款成功」会在 DWS 计入退款金额，筛选放在下一层。",
        target_table="dwd_trade_refund",
        columns=(
            ("refund_id", "退款编号"),
            ("order_id", "订单号"),
            ("order_item_id", "商品行号"),
            ("user_id", "用户编号"),
            ("shop_id", "店铺编号"),
            ("sku_code", "SKU 编码"),
            ("refund_time", "退款时间"),
            ("refund_date", "退款日期"),
            ("refund_amount_fen", "退款金额（分）"),
            ("refund_amount_yuan", "退款金额（元）"),
            ("refund_status_code", "退款状态编码"),
            ("refund_status_name", "退款状态中文"),
        ),
        starter_sql="""
CREATE OR REPLACE TABLE dwd_trade_refund AS
SELECT
    r.refund_id,
    r.order_id,
    r.order_item_id,
    r.refund_time,
    r.refund_date,
    r.refund_amount_fen,
    r.refund_amount_fen AS refund_amount_yuan,
    r.refund_status_code,
    CAST(r.refund_status_code AS VARCHAR) AS refund_status_name
FROM ods_refund AS r
""".strip(),
        reference_sql="""
CREATE OR REPLACE TABLE dwd_trade_refund AS
SELECT
    r.refund_id,
    r.order_id,
    r.order_item_id,
    o.user_id,
    o.shop_id,
    i.sku_code,
    r.refund_time,
    r.refund_date,
    r.refund_amount_fen,
    r.refund_amount_fen / 100.0 AS refund_amount_yuan,
    r.refund_status_code,
    CASE r.refund_status_code
        WHEN 1 THEN '申请中'
        WHEN 2 THEN '退款成功'
        WHEN 3 THEN '退款驳回'
        ELSE '未知'
    END AS refund_status_name
FROM ods_refund AS r
JOIN ods_order AS o
    ON r.order_id = o.order_id
JOIN ods_order_item AS i
    ON r.order_item_id = i.order_item_id
""".strip(),
        hints=(
            "refund_amount_yuan = refund_amount_fen / 100.0。R1001 的 10000 分是 100 元。",
            "JOIN ods_order 取用户和店铺，JOIN ods_order_item 取 sku_code。",
            "CASE：1 申请中，2 退款成功，3 退款驳回。不要用 WHERE 去掉申请中的 R1007。",
        ),
        keys=("refund_id",),
        mappings=(
            ("refund_id", "ods_refund.refund_id", "原样"),
            ("order_id", "ods_refund.order_id", "原样"),
            ("order_item_id", "ods_refund.order_item_id", "退到哪一个商品行"),
            ("user_id", "ods_order.user_id", "按 order_id 关联"),
            ("shop_id", "ods_order.shop_id", "按 order_id 关联"),
            ("sku_code", "ods_order_item.sku_code", "按 order_item_id 关联"),
            ("refund_time", "ods_refund.refund_time", "原样"),
            ("refund_date", "ods_refund.refund_date", "退款金额以后按这个日期汇总"),
            ("refund_amount_fen", "ods_refund.refund_amount_fen", "保留源字段，单位是分"),
            ("refund_amount_yuan", "ods_refund.refund_amount_fen", "除以 100，分转元"),
            ("refund_status_code", "ods_refund.refund_status_code", "原样保留"),
            ("refund_status_name", "ods_refund.refund_status_code", "1 申请中，2 退款成功，3 退款驳回"),
        ),
        grain="一行代表一次退款申请，金额单位已经换成元。",
    ),
    Exercise(
        id="e06_pay_dup",
        layer="DWD",
        layer_name="DWD 明细层",
        nav="支付金额排错",
        title="排错：整单支付被商品行放大",
        goal="先看到错误结果里的两行 400 元，再把实付收成每个订单一行。",
        prompt="""
O1001 有两条商品明细，但支付表只有一行：支付编号 P1001，40000 分，也就是 400 元。这 400 元是整单支付，不是球拍 400、球鞋再 400。

请先点击「运行有问题的 SQL」。结果里 O1001 会出现两行，支付金额都是 400 元，支付编号却都是 P1001。如果这时对支付金额求和，400 会被加两次，变成 800。

然后改写 SQL，生成 `ana_order_payment`：

- 一行代表一笔支付成功的订单
- 字段是 order_id、payment_id、pay_amount_yuan
- 只保留支付状态编码 2
- 同一支付编号只出现一次
- 不要 JOIN 商品明细

O1002 还在待支付，O1005 支付失败，这两笔都不要出现。O1001 的实付必须是 400 元。
""".strip(),
        caliber="支付表的粒度就是订单支付。实付不能先连到商品行再求和。",
        target_table="ana_order_payment",
        columns=(
            ("order_id", "订单号"),
            ("payment_id", "支付编号"),
            ("pay_amount_yuan", "支付成功金额（元），同一支付编号只计一次"),
        ),
        starter_sql="""
-- 下面这段 SQL 有口径问题。请先点「运行有问题的 SQL」，看完两行 400 元后再改。
-- 目标表 ana_order_payment：每个支付成功的订单一行。
-- 字段：order_id, payment_id, pay_amount_yuan
-- 不要 JOIN 商品明细，只保留 pay_status_code = 2。

SELECT
    i.order_id,
    i.order_item_id,
    p.payment_id,
    p.pay_amount_fen / 100.0 AS pay_amount_yuan
FROM ods_order_item AS i
JOIN ods_payment AS p
    ON i.order_id = p.order_id
WHERE p.pay_status_code = 2
""".strip(),
        reference_sql="""
CREATE OR REPLACE TABLE ana_order_payment AS
SELECT
    order_id,
    payment_id,
    pay_amount_fen / 100.0 AS pay_amount_yuan
FROM ods_payment
WHERE pay_status_code = 2
""".strip(),
        hints=(
            "有问题的结果里，两行的 payment_id 都是 P1001。同一笔支付被两条商品明细复制了。",
            "正确查询不要出现 ods_order_item。直接从 ods_payment 取数，支付表本身就是一订单一行。",
            "WHERE pay_status_code = 2，金额除以 100。O1001 只留下 P1001 和 400。",
        ),
        keys=("order_id",),
        bad_sql="""
SELECT
    i.order_id,
    i.order_item_id,
    i.sku_code,
    i.item_amount_yuan,
    p.payment_id,
    p.pay_amount_fen / 100.0 AS pay_amount_yuan
FROM ods_order_item AS i
JOIN ods_payment AS p
    ON i.order_id = p.order_id
WHERE i.order_id = 'O1001'
  AND p.pay_status_code = 2
""".strip(),
        bad_note="应当看到两行。商品金额是 300 和 100，支付编号都是 P1001，支付金额却都是 400 元。两行相加会变成 800 元。",
        grain="正确结果里，一行代表一笔支付成功的订单。",
    ),
    Exercise(
        id="e07_dws_user",
        layer="DWS",
        layer_name="DWS 汇总层",
        nav="用户日汇总",
        title="用户 × 日期汇总",
        goal="按用户和日期汇总订单数、下单商品金额、实付和退款。三个金额不要用同一个日期。",
        prompt="""
生成 `dws_user_1d`。请使用你已经生成的三张 DWD 表。

统计口径：

- `order_cnt`：按下单日期，数不同的订单号。未支付的订单也算下过单。
- `order_amt`：按下单日期，把商品明细金额 `item_amount_yuan` 相加。这不是实付。
- `pay_amt`：按支付日期，只加总支付状态为「支付成功」的 `pay_amount_yuan`。
- `refund_amt`：按退款日期，只加总退款状态为「退款成功」的 `refund_amount_yuan`。

三个日期对不齐时，用 UNION 收齐键再分别 LEFT JOIN。没有发生的指标写 0，不要留下空值。

张伟在 2026-03-03 没有新订单，但球鞋退款 100 元发生在这一天，这一行要保留。
""".strip(),
        caliber="下单按下单日期，实付按支付日期，退款按退款日期。订单数按不同订单号计数。",
        target_table="dws_user_1d",
        columns=(
            ("stat_date", "统计日期"),
            ("user_id", "用户编号"),
            ("order_cnt", "下单订单数，按不同订单号"),
            ("order_amt", "下单商品金额（元），商品明细金额之和"),
            ("pay_amt", "实付金额（元），仅支付成功"),
            ("refund_amt", "退款金额（元），仅退款成功"),
        ),
        starter_sql="""
CREATE OR REPLACE TABLE dws_user_1d AS
WITH orders AS (
    SELECT
        user_id,
        order_date AS stat_date,
        COUNT(DISTINCT order_id) AS order_cnt,
        SUM(item_amount_yuan) AS order_amt
    FROM dwd_trade_order_item
    GROUP BY user_id, order_date
)
SELECT
    stat_date,
    user_id,
    order_cnt,
    order_amt,
    0 AS pay_amt,
    0 AS refund_amt
FROM orders
""".strip(),
        reference_sql="""
CREATE OR REPLACE TABLE dws_user_1d AS
WITH orders AS (
    SELECT
        user_id,
        order_date AS stat_date,
        COUNT(DISTINCT order_id) AS order_cnt,
        SUM(item_amount_yuan) AS order_amt
    FROM dwd_trade_order_item
    GROUP BY user_id, order_date
),
pays AS (
    SELECT
        user_id,
        pay_date AS stat_date,
        SUM(pay_amount_yuan) AS pay_amt
    FROM dwd_trade_payment
    WHERE pay_status_name = '支付成功'
    GROUP BY user_id, pay_date
),
refunds AS (
    SELECT
        user_id,
        refund_date AS stat_date,
        SUM(refund_amount_yuan) AS refund_amt
    FROM dwd_trade_refund
    WHERE refund_status_name = '退款成功'
    GROUP BY user_id, refund_date
),
keys AS (
    SELECT user_id, stat_date FROM orders
    UNION
    SELECT user_id, stat_date FROM pays
    UNION
    SELECT user_id, stat_date FROM refunds
)
SELECT
    k.stat_date,
    k.user_id,
    COALESCE(o.order_cnt, 0) AS order_cnt,
    COALESCE(o.order_amt, 0) AS order_amt,
    COALESCE(p.pay_amt, 0) AS pay_amt,
    COALESCE(r.refund_amt, 0) AS refund_amt
FROM keys AS k
LEFT JOIN orders AS o
    ON k.user_id = o.user_id AND k.stat_date = o.stat_date
LEFT JOIN pays AS p
    ON k.user_id = p.user_id AND k.stat_date = p.stat_date
LEFT JOIN refunds AS r
    ON k.user_id = r.user_id AND k.stat_date = r.stat_date
""".strip(),
        hints=(
            "不要把三个指标放进同一个 GROUP BY。下单日期、支付日期、退款日期不是一回事。",
            "实付只保留 pay_status_name = '支付成功'。李娜 3 月 1 日有两笔订单，但待支付的 80 元不能进实付，实付是 600。",
            "退款只保留「退款成功」，日期用 refund_date。张伟 3 月 3 日没有订单，退款 100 元这一行也要在。",
            "用 UNION 收集 user_id 和 stat_date，再 LEFT JOIN 三段汇总，空值用 COALESCE 写成 0。",
        ),
        keys=("stat_date", "user_id"),
        mappings=(
            ("order_cnt", "dwd_trade_order_item.order_id", "按下单日期，COUNT DISTINCT 订单号，含未支付"),
            ("order_amt", "dwd_trade_order_item.item_amount_yuan", "按下单日期求和，这是商品明细金额"),
            ("pay_amt", "dwd_trade_payment.pay_amount_yuan", "按支付日期求和，且支付状态为支付成功"),
            ("refund_amt", "dwd_trade_refund.refund_amount_yuan", "按退款日期求和，且退款状态为退款成功"),
        ),
        deps=("e03_dwd_item", "e04_dwd_pay", "e05_dwd_refund"),
        ref_deps=("e03_dwd_item", "e04_dwd_pay", "e05_dwd_refund"),
        grain="一行代表一个用户在一个统计日上的汇总。某一天只有退款、没有下单时，也要有这一行。",
    ),
    Exercise(
        id="e08_dws_sku",
        layer="DWS",
        layer_name="DWS 汇总层",
        nav="商品日汇总",
        title="SKU × 日期汇总",
        goal="商品销售额先用商品明细金额。支付表是整单金额，不要分摊到 SKU 上。",
        prompt="""
生成 `dws_sku_1d`。

统计口径：

- `sale_qty`、`sale_amt`、`order_cnt` 按下单日期，从 `dwd_trade_order_item` 汇总。
- `sale_amt` 是商品销售额，等于商品明细金额 `item_amount_yuan` 之和。含未支付订单，不扣退款，也不使用支付表。
- `order_cnt` 按不同订单号计数。
- `refund_amt` 按退款日期，只汇总退款成功的金额，退到对应 SKU。

3 月 3 日羽毛球鞋没有新的下单，但有 O1001 的 100 元成功退款。这一天要保留：销售额 0，退款 100。商品名称从 `dim_sku` 取，不能只从当天的销售记录里取。
""".strip(),
        caliber="商品销售额 = 下单商品明细金额，按下单日期，不扣退款。退款按退款日期记到 SKU。不做支付金额分摊。",
        target_table="dws_sku_1d",
        columns=(
            ("stat_date", "统计日期"),
            ("sku_id", "SKU 主键"),
            ("sku_code", "SKU 编码"),
            ("sku_name", "商品名称"),
            ("category_name", "品类"),
            ("sale_qty", "下单件数"),
            ("sale_amt", "商品销售额（元），即商品明细金额之和"),
            ("order_cnt", "下单订单数"),
            ("refund_amt", "退款成功金额（元）"),
        ),
        starter_sql="""
CREATE OR REPLACE TABLE dws_sku_1d AS
SELECT
    order_date AS stat_date,
    sku_id,
    sku_code,
    sku_name,
    category_name,
    SUM(quantity) AS sale_qty,
    SUM(item_amount_yuan) AS sale_amt,
    COUNT(DISTINCT order_id) AS order_cnt,
    0 AS refund_amt
FROM dwd_trade_order_item
GROUP BY order_date, sku_id, sku_code, sku_name, category_name
""".strip(),
        reference_sql="""
CREATE OR REPLACE TABLE dws_sku_1d AS
WITH sales AS (
    SELECT
        order_date AS stat_date,
        sku_id,
        sku_code,
        sku_name,
        category_name,
        SUM(quantity) AS sale_qty,
        SUM(item_amount_yuan) AS sale_amt,
        COUNT(DISTINCT order_id) AS order_cnt
    FROM dwd_trade_order_item
    GROUP BY order_date, sku_id, sku_code, sku_name, category_name
),
refunds AS (
    SELECT
        r.refund_date AS stat_date,
        s.sku_id,
        s.sku_code,
        s.sku_name,
        s.category_name,
        SUM(r.refund_amount_yuan) AS refund_amt
    FROM dwd_trade_refund AS r
    JOIN dim_sku AS s
        ON r.sku_code = s.sku_code
    WHERE r.refund_status_name = '退款成功'
    GROUP BY r.refund_date, s.sku_id, s.sku_code, s.sku_name, s.category_name
),
keys AS (
    SELECT stat_date, sku_id FROM sales
    UNION
    SELECT stat_date, sku_id FROM refunds
)
SELECT
    k.stat_date,
    COALESCE(sa.sku_id, rf.sku_id) AS sku_id,
    COALESCE(sa.sku_code, rf.sku_code) AS sku_code,
    COALESCE(sa.sku_name, rf.sku_name) AS sku_name,
    COALESCE(sa.category_name, rf.category_name) AS category_name,
    COALESCE(sa.sale_qty, 0) AS sale_qty,
    COALESCE(sa.sale_amt, 0) AS sale_amt,
    COALESCE(sa.order_cnt, 0) AS order_cnt,
    COALESCE(rf.refund_amt, 0) AS refund_amt
FROM keys AS k
LEFT JOIN sales AS sa
    ON k.stat_date = sa.stat_date AND k.sku_id = sa.sku_id
LEFT JOIN refunds AS rf
    ON k.stat_date = rf.stat_date AND k.sku_id = rf.sku_id
""".strip(),
        hints=(
            "销售一段只查 dwd_trade_order_item，按 order_date 和 SKU 汇总。sale_amt 用 item_amount_yuan，不要减退款。",
            "退款一段只留退款成功，按 refund_date 汇总，并用 sku_code 关联 dim_sku 拿到名称。",
            "3 月 3 日的羽毛球鞋只有退款、没有销售。键要用 UNION 收进来，sale_amt 为 0，refund_amt 为 100。",
        ),
        keys=("stat_date", "sku_id"),
        mappings=(
            ("sale_qty", "dwd_trade_order_item.quantity", "按下单日期求和"),
            ("sale_amt", "dwd_trade_order_item.item_amount_yuan", "商品销售额，按下单日期求和，不扣退款"),
            ("order_cnt", "dwd_trade_order_item.order_id", "按下单日期，COUNT DISTINCT 订单号"),
            ("refund_amt", "dwd_trade_refund.refund_amount_yuan", "按退款日期求和，且退款成功"),
        ),
        deps=("e03_dwd_item", "e05_dwd_refund"),
        ref_deps=("e03_dwd_item", "e05_dwd_refund"),
        grain="一行代表一个 SKU 在一个统计日上的销售和退款。当天只有退款时也保留。",
    ),
    Exercise(
        id="e09_dws_shop",
        layer="DWS",
        layer_name="DWS 汇总层",
        nav="店铺日汇总",
        title="店铺 × 日期汇总",
        goal="把用户日汇总的同一套口径，改到店铺粒度上再做一次。",
        prompt="""
生成 `dws_shop_1d`。口径和用户日汇总相同，只是粒度换成店铺：

- 下单订单数、下单商品金额：按下单日期，来自 `dwd_trade_order_item`
- 实付：按支付日期，只算支付成功，来自 `dwd_trade_payment`
- 退款：按退款日期，只算退款成功，来自 `dwd_trade_refund`

羽动体育 S001 在 2026-03-03 没有新订单，但有 O1001 的 100 元退款。这一行的订单数和实付是 0，退款是 100。

订单数继续按不同订单号计数。一家店一天有多笔订单时，不要数成 1。
""".strip(),
        caliber="下单按下单日期，实付按支付日期，退款按退款日期。订单数按不同订单号计数。",
        target_table="dws_shop_1d",
        columns=(
            ("stat_date", "统计日期"),
            ("shop_id", "店铺编号"),
            ("order_cnt", "下单订单数"),
            ("order_amt", "下单商品金额（元）"),
            ("pay_amt", "实付金额（元）"),
            ("refund_amt", "退款金额（元）"),
        ),
        starter_sql="""
CREATE OR REPLACE TABLE dws_shop_1d AS
SELECT
    order_date AS stat_date,
    shop_id,
    COUNT(DISTINCT order_id) AS order_cnt,
    SUM(item_amount_yuan) AS order_amt,
    0 AS pay_amt,
    0 AS refund_amt
FROM dwd_trade_order_item
GROUP BY order_date, shop_id
""".strip(),
        reference_sql="""
CREATE OR REPLACE TABLE dws_shop_1d AS
WITH orders AS (
    SELECT
        shop_id,
        order_date AS stat_date,
        COUNT(DISTINCT order_id) AS order_cnt,
        SUM(item_amount_yuan) AS order_amt
    FROM dwd_trade_order_item
    GROUP BY shop_id, order_date
),
pays AS (
    SELECT
        shop_id,
        pay_date AS stat_date,
        SUM(pay_amount_yuan) AS pay_amt
    FROM dwd_trade_payment
    WHERE pay_status_name = '支付成功'
    GROUP BY shop_id, pay_date
),
refunds AS (
    SELECT
        shop_id,
        refund_date AS stat_date,
        SUM(refund_amount_yuan) AS refund_amt
    FROM dwd_trade_refund
    WHERE refund_status_name = '退款成功'
    GROUP BY shop_id, refund_date
),
keys AS (
    SELECT shop_id, stat_date FROM orders
    UNION
    SELECT shop_id, stat_date FROM pays
    UNION
    SELECT shop_id, stat_date FROM refunds
)
SELECT
    k.stat_date,
    k.shop_id,
    COALESCE(o.order_cnt, 0) AS order_cnt,
    COALESCE(o.order_amt, 0) AS order_amt,
    COALESCE(p.pay_amt, 0) AS pay_amt,
    COALESCE(r.refund_amt, 0) AS refund_amt
FROM keys AS k
LEFT JOIN orders AS o
    ON k.shop_id = o.shop_id AND k.stat_date = o.stat_date
LEFT JOIN pays AS p
    ON k.shop_id = p.shop_id AND k.stat_date = p.stat_date
LEFT JOIN refunds AS r
    ON k.shop_id = r.shop_id AND k.stat_date = r.stat_date
""".strip(),
        hints=(
            "结构和用户日汇总一样，把 user_id 换成 shop_id。",
            "支付、退款都要从各自的 DWD 表汇总，不能只在订单明细上左连接同一天的金额。",
            "S001 在 3 月 3 日只有退款。UNION 收键之后，这一行 order_cnt = 0，pay_amt = 0，refund_amt = 100。",
        ),
        keys=("stat_date", "shop_id"),
        mappings=(
            ("order_cnt", "dwd_trade_order_item.order_id", "按下单日期，COUNT DISTINCT 订单号"),
            ("order_amt", "dwd_trade_order_item.item_amount_yuan", "按下单日期求和"),
            ("pay_amt", "dwd_trade_payment.pay_amount_yuan", "按支付日期求和，且支付成功"),
            ("refund_amt", "dwd_trade_refund.refund_amount_yuan", "按退款日期求和，且退款成功"),
        ),
        deps=("e03_dwd_item", "e04_dwd_pay", "e05_dwd_refund"),
        ref_deps=("e03_dwd_item", "e04_dwd_pay", "e05_dwd_refund"),
        grain="一行代表一个店铺在一个统计日上的汇总。",
    ),
    Exercise(
        id="e10_ads_daily",
        layer="ADS",
        layer_name="ADS 应用层",
        nav="运营日报",
        title="运营日报",
        goal="从用户日汇总做出每天一行的运营日报。看板会直接读这张表。",
        prompt="""
生成 `ads_ops_daily`。参考实现从 `dws_user_1d` 汇总，不从店铺表汇总。

每个用户的订单不会跨用户重复，所以日报订单数可以把用户日汇总的 `order_cnt` 相加。`order_amt`、`pay_amt`、`refund_amt` 同样按 `stat_date` 求和。

`net_pay_amt` = 当天实付减当天退款。它的意思是「这一天收到的钱，减去这一天退出去的钱」，不是把某笔订单从下单日扣到退款日。

请 JOIN `dim_date`，用 `date_day = stat_date` 补上 `weekday_name`。2026-03-01 是星期日。

核对时注意：O1001 的实付是 400 元，但 3 月 1 日还有 O1006 的 600 元支付成功，O1002 的 80 元未成功。这一天的日报实付不是 400。
""".strip(),
        caliber="日报指标从用户日汇总再按统计日期求和。净额 = 当日实付 − 当日退款，两个指标各自带着原来的日期口径。",
        target_table="ads_ops_daily",
        columns=(
            ("stat_date", "统计日期"),
            ("weekday_name", "星期"),
            ("order_cnt", "下单订单数"),
            ("order_amt", "下单商品金额（元）"),
            ("pay_amt", "实付金额（元）"),
            ("refund_amt", "退款金额（元）"),
            ("net_pay_amt", "当日实付减当日退款（元）"),
        ),
        starter_sql="""
CREATE OR REPLACE TABLE ads_ops_daily AS
SELECT
    stat_date,
    SUM(order_cnt) AS order_cnt,
    SUM(order_amt) AS order_amt,
    SUM(pay_amt) AS pay_amt,
    SUM(refund_amt) AS refund_amt
FROM dws_user_1d
GROUP BY stat_date
""".strip(),
        reference_sql="""
CREATE OR REPLACE TABLE ads_ops_daily AS
SELECT
    u.stat_date,
    d.weekday_name,
    SUM(u.order_cnt) AS order_cnt,
    SUM(u.order_amt) AS order_amt,
    SUM(u.pay_amt) AS pay_amt,
    SUM(u.refund_amt) AS refund_amt,
    SUM(u.pay_amt) - SUM(u.refund_amt) AS net_pay_amt
FROM dws_user_1d AS u
JOIN dim_date AS d
    ON u.stat_date = d.date_day
GROUP BY u.stat_date, d.weekday_name
""".strip(),
        hints=(
            "FROM dws_user_1d，按 stat_date 求和。这是参考路径，不要改去读店铺表。",
            "3 月 1 日实付不是 O1001 单独的 400，还要加上当天另一笔支付成功的 600，并且不要加上未成功的 80。",
            "net_pay_amt 用当天 pay_amt 减当天 refund_amt。3 月 3 日的退款不要挪回 3 月 1 日。",
            "JOIN dim_date ON u.stat_date = d.date_day，取出 weekday_name。",
        ),
        keys=("stat_date",),
        mappings=(
            ("order_cnt", "dws_user_1d.order_cnt", "按 stat_date 求和"),
            ("order_amt", "dws_user_1d.order_amt", "按 stat_date 求和"),
            ("pay_amt", "dws_user_1d.pay_amt", "按 stat_date 求和。这就是日报上的实付金额"),
            ("refund_amt", "dws_user_1d.refund_amt", "按 stat_date 求和"),
            ("net_pay_amt", "pay_amt - refund_amt", "同一统计日的实付减实退"),
            ("weekday_name", "dim_date.weekday_name", "date_day = stat_date"),
        ),
        deps=("e07_dws_user",),
        ref_deps=("e03_dwd_item", "e04_dwd_pay", "e05_dwd_refund", "e07_dws_user"),
        grain="一行代表一个统计日的运营日报。",
    ),
    Exercise(
        id="e11_ads_rank",
        layer="ADS",
        layer_name="ADS 应用层",
        nav="商品排行榜",
        title="每日商品排行榜",
        goal="按商品销售额给每天的 SKU 排名。这道题要求结果按日期和名次排列。",
        prompt="""
生成 `ads_sku_rank_1d`，数据来自 `dws_sku_1d`。

排行依据是 `sale_amt`（下单商品明细金额），从高到低。当天没有销售额的 SKU 不进榜，所以 3 月 3 日只有退款的羽毛球鞋不要出现。

名次用 `ROW_NUMBER()`，按 `stat_date` 分区。销售额相同的时候，按 `sku_code` 升序决定先后。

请让表中的行按 `stat_date`、`rank_no` 升序排列。判题会检查这个顺序。3 月 1 日销售额最高的是羽毛球拍。
""".strip(),
        caliber="排行榜只看商品销售额 sale_amt，不扣退款，也不使用支付金额。当日 sale_amt 为 0 的 SKU 不进入榜单。",
        target_table="ads_sku_rank_1d",
        columns=(
            ("stat_date", "统计日期"),
            ("rank_no", "名次，从 1 开始"),
            ("sku_id", "SKU 主键"),
            ("sku_code", "SKU 编码"),
            ("sku_name", "商品名称"),
            ("category_name", "品类"),
            ("sale_qty", "下单件数"),
            ("sale_amt", "商品销售额（元）"),
            ("order_cnt", "下单订单数"),
        ),
        starter_sql="""
CREATE OR REPLACE TABLE ads_sku_rank_1d AS
SELECT
    stat_date,
    sku_id,
    sku_code,
    sku_name,
    category_name,
    sale_qty,
    sale_amt,
    order_cnt
FROM dws_sku_1d
WHERE sale_amt > 0
""".strip(),
        reference_sql="""
CREATE OR REPLACE TABLE ads_sku_rank_1d AS
SELECT
    stat_date,
    ROW_NUMBER() OVER (
        PARTITION BY stat_date
        ORDER BY sale_amt DESC, sku_code ASC
    ) AS rank_no,
    sku_id,
    sku_code,
    sku_name,
    category_name,
    sale_qty,
    sale_amt,
    order_cnt
FROM dws_sku_1d
WHERE sale_amt > 0
ORDER BY stat_date, rank_no
""".strip(),
        hints=(
            "WHERE sale_amt > 0，去掉只有退款、没有销售额的行。",
            "ROW_NUMBER() OVER (PARTITION BY stat_date ORDER BY sale_amt DESC, sku_code ASC) AS rank_no。",
            "SQL 最后写 ORDER BY stat_date, rank_no。3 月 1 日第一名是羽毛球拍。",
        ),
        keys=("stat_date", "sku_id"),
        order_sensitive=True,
        mappings=(
            ("sale_amt", "dws_sku_1d.sale_amt", "排行依据，商品明细金额，不扣退款"),
            ("rank_no", "sale_amt DESC, sku_code ASC", "每个统计日内的 ROW_NUMBER"),
        ),
        deps=("e08_dws_sku",),
        ref_deps=("e03_dwd_item", "e05_dwd_refund", "e08_dws_sku"),
        grain="一行代表某个 SKU 在某一天的名次。只包含当天有销售额的商品。",
    ),
    Exercise(
        id="e12_lineage",
        layer="LINEAGE",
        layer_name="数据血缘",
        nav="实付金额血缘",
        title="追实付金额的血缘",
        goal="从运营日报的实付金额往回追，直到 ODS 源字段，并写清筛选和汇总规则。",
        prompt="""
从运营日报的「实付金额」出发，填写它用了哪个 ADS 字段、哪张 DWS 表、哪张 DWD 表，最后落到哪张 ODS 表的哪个字段。

同时写上单位转换、状态筛选、日期口径，以及 DWS 和 ADS 两层分别怎么汇总。

请按本实训参考 SQL 的实现路径填写。店铺日汇总如果口径一致，加总后也能得到同一个实付，但参考实现走的是用户日汇总，血缘不要改走另一条路。

提交后会展示参考链路。这条链路和「支付明细」「用户日汇总」「运营日报」三道题的参考 SQL 是同一条。
""".strip(),
        caliber="实付金额的源字段是 ods_payment.pay_amount_fen。日期是支付日期。只有支付成功进入汇总。",
        target_table="",
        columns=(),
        starter_sql="",
        reference_sql="",
        hints=(
            "日报字段是 ads_ops_daily.pay_amt，不是下单商品金额，也不是净额。",
            "参考 SQL 读的是 dws_user_1d.pay_amt。DWS 又只汇总了支付明细里「支付成功」的 pay_amount_yuan。",
            "pay_amount_yuan 来自 ods_payment.pay_amount_fen 除以 100。关联订单主表只是为了拿到用户和店铺，金额不来自商品明细。",
        ),
        keys=(),
        deps=("e10_ads_daily",),
        kind="lineage",
        grain="这道题不生成新表，填写实付金额的加工路径。",
    ),
)


_BY_ID = {exercise.id: exercise for exercise in EXERCISES}


def get_exercise(exercise_id: str) -> Exercise:
    return _BY_ID[exercise_id]


def exercises_by_layer() -> list[tuple[str, list[Exercise]]]:
    grouped: list[tuple[str, list[Exercise]]] = []
    for exercise in EXERCISES:
        if not grouped or grouped[-1][0] != exercise.layer_name:
            grouped.append((exercise.layer_name, [exercise]))
        else:
            grouped[-1][1].append(exercise)
    return grouped


def student_table_meta(table_name: str) -> dict | None:
    for exercise in EXERCISES:
        if exercise.target_table == table_name:
            return {
                "layer": exercise.layer_name,
                "title": exercise.title,
                "grain": exercise.grain,
                "columns": [(name, "", comment) for name, comment in exercise.columns],
            }
    return None
