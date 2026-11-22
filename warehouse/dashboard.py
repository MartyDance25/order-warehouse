"""看板只读取学员当前生成的结果表。"""

from __future__ import annotations

import pandas as pd

from warehouse.db import table_exists
from warehouse.sqlutil import quote_ident

DAILY_TABLE = "ads_ops_daily"
RANK_TABLE = "ads_sku_rank_1d"
DAILY_COLUMNS = [
    "stat_date",
    "weekday_name",
    "order_cnt",
    "order_amt",
    "pay_amt",
    "refund_amt",
    "net_pay_amt",
]
RANK_COLUMNS = [
    "stat_date",
    "rank_no",
    "sku_name",
    "category_name",
    "sale_qty",
    "sale_amt",
    "order_cnt",
]


def _missing_columns(frame: pd.DataFrame, columns: list[str]) -> list[str]:
    have = {name.lower() for name in frame.columns}
    return [name for name in columns if name not in have]


def read_daily(con) -> tuple[pd.DataFrame | None, str]:
    if not table_exists(con, DAILY_TABLE):
        return None, "还没有运营日报。完成「运营日报」后，这里会读取你生成的 ads_ops_daily。"
    frame = con.execute(f"SELECT * FROM {quote_ident(DAILY_TABLE)}").fetchdf()
    missing = _missing_columns(frame, DAILY_COLUMNS)
    if missing:
        return None, "ads_ops_daily 缺少字段：" + "、".join(missing) + "。请按题目的目标结构重新生成。"
    frame.columns = [name.lower() for name in frame.columns]
    view = frame[DAILY_COLUMNS].sort_values("stat_date")
    return view, ""


def read_rank(con) -> tuple[pd.DataFrame | None, str]:
    if not table_exists(con, RANK_TABLE):
        return None, "还没有每日商品排行榜。完成「商品排行榜」后，这里会读取你生成的 ads_sku_rank_1d。"
    frame = con.execute(f"SELECT * FROM {quote_ident(RANK_TABLE)}").fetchdf()
    missing = _missing_columns(frame, RANK_COLUMNS)
    if missing:
        return None, "ads_sku_rank_1d 缺少字段：" + "、".join(missing) + "。请按题目的目标结构重新生成。"
    frame.columns = [name.lower() for name in frame.columns]
    view = frame[RANK_COLUMNS].sort_values(["stat_date", "rank_no"])
    return view, ""


def read_user_daily(con) -> pd.DataFrame | None:
    if not table_exists(con, "dws_user_1d") or not table_exists(con, "dim_user"):
        return None
    return con.execute(
        """
        SELECT
            u.stat_date,
            u.user_id,
            s.user_name,
            u.order_cnt,
            u.order_amt,
            u.pay_amt,
            u.refund_amt
        FROM dws_user_1d u
        LEFT JOIN dim_user s ON u.user_id = s.user_id
        ORDER BY u.stat_date, u.user_id
        """
    ).fetchdf()
