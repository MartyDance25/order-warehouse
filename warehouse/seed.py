"""装入可手算的电商模拟数据。金额在贴源支付、退款表里用分，订单和商品明细用元。"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

import duckdb

D = Decimal


def _yuan(text: str) -> Decimal:
    return D(text)


def load_seed(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(
        """
        CREATE TABLE ods_order (
            order_id VARCHAR PRIMARY KEY,
            user_id VARCHAR NOT NULL,
            shop_id VARCHAR NOT NULL,
            order_time TIMESTAMP NOT NULL,
            order_date DATE NOT NULL,
            order_status_code INTEGER NOT NULL,
            item_amount_yuan DECIMAL(18,2) NOT NULL
        )
        """
    )
    con.execute(
        """
        CREATE TABLE ods_order_item (
            order_item_id VARCHAR PRIMARY KEY,
            order_id VARCHAR NOT NULL,
            sku_code VARCHAR NOT NULL,
            quantity INTEGER NOT NULL,
            item_amount_yuan DECIMAL(18,2) NOT NULL
        )
        """
    )
    con.execute(
        """
        CREATE TABLE ods_payment (
            payment_id VARCHAR PRIMARY KEY,
            order_id VARCHAR NOT NULL,
            pay_time TIMESTAMP NOT NULL,
            pay_date DATE NOT NULL,
            pay_amount_fen BIGINT NOT NULL,
            pay_status_code INTEGER NOT NULL
        )
        """
    )
    con.execute(
        """
        CREATE TABLE ods_refund (
            refund_id VARCHAR PRIMARY KEY,
            order_id VARCHAR NOT NULL,
            order_item_id VARCHAR NOT NULL,
            refund_time TIMESTAMP NOT NULL,
            refund_date DATE NOT NULL,
            refund_amount_fen BIGINT NOT NULL,
            refund_status_code INTEGER NOT NULL
        )
        """
    )
    con.execute(
        """
        CREATE TABLE dim_user (
            user_id VARCHAR PRIMARY KEY,
            user_name VARCHAR NOT NULL,
            city VARCHAR NOT NULL,
            register_date DATE NOT NULL
        )
        """
    )
    con.execute(
        """
        CREATE TABLE dim_shop (
            shop_id VARCHAR PRIMARY KEY,
            shop_name VARCHAR NOT NULL,
            shop_type VARCHAR NOT NULL
        )
        """
    )
    con.execute(
        """
        CREATE TABLE dim_sku (
            sku_id VARCHAR PRIMARY KEY,
            sku_code VARCHAR NOT NULL UNIQUE,
            sku_name VARCHAR NOT NULL,
            category_name VARCHAR NOT NULL,
            shop_id VARCHAR NOT NULL,
            list_price_yuan DECIMAL(18,2) NOT NULL
        )
        """
    )
    con.execute(
        """
        CREATE TABLE dim_date (
            date_day DATE PRIMARY KEY,
            year_num INTEGER NOT NULL,
            month_num INTEGER NOT NULL,
            day_num INTEGER NOT NULL,
            weekday_name VARCHAR NOT NULL,
            is_weekend BOOLEAN NOT NULL
        )
        """
    )

    con.executemany(
        "INSERT INTO dim_user VALUES (?, ?, ?, ?)",
        [
            ("U001", "张伟", "杭州", date(2024, 6, 1)),
            ("U002", "李娜", "成都", date(2024, 11, 18)),
            ("U003", "王磊", "武汉", date(2025, 1, 9)),
            ("U004", "陈静", "南京", date(2025, 8, 21)),
        ],
    )
    con.executemany(
        "INSERT INTO dim_shop VALUES (?, ?, ?)",
        [
            ("S001", "羽动体育旗舰店", "自营"),
            ("S002", "城市跑步专营店", "专营"),
        ],
    )
    con.executemany(
        "INSERT INTO dim_sku VALUES (?, ?, ?, ?, ?, ?)",
        [
            ("SKU101", "YJ-RACKET-01", "羽毛球拍", "球拍", "S001", _yuan("300.00")),
            ("SKU102", "YJ-SHOE-01", "羽毛球鞋", "球鞋", "S001", _yuan("100.00")),
            ("SKU201", "YJ-CUP-01", "运动水杯", "配件", "S002", _yuan("40.00")),
            ("SKU202", "YJ-SHORT-01", "跑步短裤", "服饰", "S002", _yuan("150.00")),
        ],
    )

    weekdays = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]
    start = date(2026, 3, 1)
    date_rows = []
    for offset in range(7):
        day = start + timedelta(days=offset)
        date_rows.append(
            (
                day,
                day.year,
                day.month,
                day.day,
                weekdays[day.weekday()],
                day.weekday() >= 5,
            )
        )
    con.executemany("INSERT INTO dim_date VALUES (?, ?, ?, ?, ?, ?)", date_rows)

    # 订单状态：10 待支付，20 已支付，30 部分退款
    con.executemany(
        "INSERT INTO ods_order VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            ("O1001", "U001", "S001", datetime(2026, 3, 1, 10, 15), date(2026, 3, 1), 30, _yuan("400.00")),
            ("O1002", "U002", "S002", datetime(2026, 3, 1, 16, 40), date(2026, 3, 1), 10, _yuan("80.00")),
            ("O1003", "U003", "S001", datetime(2026, 3, 2, 9, 5), date(2026, 3, 2), 20, _yuan("300.00")),
            ("O1004", "U001", "S002", datetime(2026, 3, 2, 20, 30), date(2026, 3, 2), 30, _yuan("190.00")),
            ("O1005", "U004", "S001", datetime(2026, 3, 5, 8, 0), date(2026, 3, 5), 10, _yuan("100.00")),
            ("O1006", "U002", "S001", datetime(2026, 3, 1, 11, 0), date(2026, 3, 1), 20, _yuan("600.00")),
            ("O1007", "U003", "S002", datetime(2026, 3, 3, 15, 0), date(2026, 3, 3), 20, _yuan("150.00")),
            ("O1008", "U004", "S002", datetime(2026, 3, 4, 9, 0), date(2026, 3, 4), 20, _yuan("120.00")),
        ],
    )
    con.executemany(
        "INSERT INTO ods_order_item VALUES (?, ?, ?, ?, ?)",
        [
            ("OI10011", "O1001", "YJ-RACKET-01", 1, _yuan("300.00")),
            ("OI10012", "O1001", "YJ-SHOE-01", 1, _yuan("100.00")),
            ("OI10021", "O1002", "YJ-CUP-01", 2, _yuan("80.00")),
            ("OI10031", "O1003", "YJ-RACKET-01", 1, _yuan("300.00")),
            ("OI10041", "O1004", "YJ-SHORT-01", 1, _yuan("150.00")),
            ("OI10042", "O1004", "YJ-CUP-01", 1, _yuan("40.00")),
            ("OI10051", "O1005", "YJ-SHOE-01", 1, _yuan("100.00")),
            ("OI10061", "O1006", "YJ-RACKET-01", 2, _yuan("600.00")),
            ("OI10071", "O1007", "YJ-SHORT-01", 1, _yuan("150.00")),
            ("OI10081", "O1008", "YJ-CUP-01", 3, _yuan("120.00")),
        ],
    )
    # 支付状态：1 待支付，2 支付成功，3 支付失败
    con.executemany(
        "INSERT INTO ods_payment VALUES (?, ?, ?, ?, ?, ?)",
        [
            ("P1001", "O1001", datetime(2026, 3, 1, 10, 20), date(2026, 3, 1), 40000, 2),
            ("P1002", "O1002", datetime(2026, 3, 1, 16, 45), date(2026, 3, 1), 8000, 1),
            ("P1003", "O1003", datetime(2026, 3, 2, 9, 8), date(2026, 3, 2), 30000, 2),
            ("P1004", "O1004", datetime(2026, 3, 2, 20, 35), date(2026, 3, 2), 19000, 2),
            ("P1005", "O1005", datetime(2026, 3, 5, 8, 2), date(2026, 3, 5), 10000, 3),
            ("P1006", "O1006", datetime(2026, 3, 1, 11, 5), date(2026, 3, 1), 60000, 2),
            ("P1007", "O1007", datetime(2026, 3, 3, 15, 10), date(2026, 3, 3), 15000, 2),
            ("P1008", "O1008", datetime(2026, 3, 4, 9, 5), date(2026, 3, 4), 12000, 2),
        ],
    )
    # 退款状态：1 申请中，2 退款成功
    con.executemany(
        "INSERT INTO ods_refund VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            ("R1001", "O1001", "OI10012", datetime(2026, 3, 3, 14, 6), date(2026, 3, 3), 10000, 2),
            ("R1004", "O1004", "OI10042", datetime(2026, 3, 4, 11, 20), date(2026, 3, 4), 4000, 2),
            ("R1007", "O1007", "OI10071", datetime(2026, 3, 3, 18, 30), date(2026, 3, 3), 15000, 1),
        ],
    )
    _assert_seed(con)


def _assert_seed(con: duckdb.DuckDBPyConnection) -> None:
    mismatch = con.execute(
        """
        SELECT o.order_id
        FROM ods_order o
        JOIN (
            SELECT order_id, SUM(item_amount_yuan) AS amt
            FROM ods_order_item
            GROUP BY order_id
        ) i ON o.order_id = i.order_id
        WHERE o.item_amount_yuan <> i.amt
        """
    ).fetchall()
    if mismatch:
        raise RuntimeError(f"订单主表金额与明细不一致: {mismatch}")

    pay_mismatch = con.execute(
        """
        SELECT o.order_id
        FROM ods_order o
        JOIN ods_payment p ON o.order_id = p.order_id
        WHERE p.pay_amount_fen <> CAST(o.item_amount_yuan * 100 AS BIGINT)
        """
    ).fetchall()
    if pay_mismatch:
        raise RuntimeError(f"支付金额（分）与订单商品金额不一致: {pay_mismatch}")

    o1001_items = con.execute(
        "SELECT COUNT(*) FROM ods_order_item WHERE order_id = 'O1001'"
    ).fetchone()[0]
    o1001_pay = con.execute(
        "SELECT pay_amount_fen, pay_status_code FROM ods_payment WHERE order_id = 'O1001'"
    ).fetchone()
    o1001_refund = con.execute(
        """
        SELECT refund_amount_fen, refund_date, refund_status_code
        FROM ods_refund WHERE order_id = 'O1001'
        """
    ).fetchone()
    if o1001_items != 2 or o1001_pay != (40000, 2) or o1001_refund != (10000, date(2026, 3, 3), 2):
        raise RuntimeError("O1001 手算订单与设计不一致")

    sunday = con.execute(
        "SELECT weekday_name FROM dim_date WHERE date_day = DATE '2026-03-01'"
    ).fetchone()[0]
    if sunday != "星期日":
        raise RuntimeError(f"2026-03-01 应为星期日，实际是 {sunday}")
