"""拆分学员 SQL，并限制在实训库里能做的事。"""

from __future__ import annotations

import re

QUERY_HEADS = {"select", "with", "describe", "desc", "summarize", "show", "from", "values"}
PROTECTED_PREFIXES = ("ods_", "dim_")

_CREATE_RE = re.compile(
    r"^create\s+(?:or\s+replace\s+)?table\s+(?:if\s+not\s+exists\s+)?([a-z_][a-z0-9_]*)\s+as\b",
    re.IGNORECASE | re.DOTALL,
)
_DROP_RE = re.compile(
    r"^drop\s+table\s+(?:if\s+exists\s+)?([a-z_][a-z0-9_]*)\s*$",
    re.IGNORECASE | re.DOTALL,
)
_BANNED = [
    (
        re.compile(r"\bread_[a-z0-9_]*\b", re.IGNORECASE),
        "不能读取数据库以外的文件。请只使用实训台里的表。",
    ),
    (
        re.compile(r"\b(attach|install|load|copy|export|import|pragma|call|set|reset|alter|truncate|grant|revoke|vacuum|checkpoint|insert|update|delete)\b", re.IGNORECASE),
        "这条语句包含不允许的操作。请只编写查询，或用 CREATE TABLE AS 保存结果。",
    ),
    (
        re.compile(r"https?://|s3://", re.IGNORECASE),
        "不能访问外部地址。",
    ),
    (
        re.compile(r"\bgetenv\b", re.IGNORECASE),
        "不能读取环境变量。",
    ),
]


def split_sql(sql: str) -> list[str]:
    parts: list[str] = []
    buf: list[str] = []
    i = 0
    n = len(sql)
    in_single = False
    in_double = False
    in_line = False
    in_block = False
    while i < n:
        ch = sql[i]
        nxt = sql[i + 1] if i + 1 < n else ""
        if in_line:
            buf.append(ch)
            if ch == "\n":
                in_line = False
            i += 1
            continue
        if in_block:
            buf.append(ch)
            if ch == "*" and nxt == "/":
                buf.append(nxt)
                i += 2
                in_block = False
            else:
                i += 1
            continue
        if in_single:
            buf.append(ch)
            if ch == "'" and nxt == "'":
                buf.append(nxt)
                i += 2
                continue
            if ch == "'":
                in_single = False
            i += 1
            continue
        if in_double:
            buf.append(ch)
            if ch == '"':
                in_double = False
            i += 1
            continue
        if ch == "-" and nxt == "-":
            in_line = True
            buf.append(ch)
            i += 1
            continue
        if ch == "/" and nxt == "*":
            in_block = True
            buf.append(ch)
            i += 1
            continue
        if ch == "'":
            in_single = True
            buf.append(ch)
            i += 1
            continue
        if ch == '"':
            in_double = True
            buf.append(ch)
            i += 1
            continue
        if ch == ";":
            stmt = "".join(buf).strip()
            if stmt:
                parts.append(stmt)
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    tail = "".join(buf).strip()
    if tail:
        parts.append(tail)
    return parts


def remove_comments(sql: str) -> str:
    out: list[str] = []
    i = 0
    n = len(sql)
    in_single = False
    while i < n:
        ch = sql[i]
        nxt = sql[i + 1] if i + 1 < n else ""
        if in_single:
            out.append(ch)
            if ch == "'" and nxt == "'":
                out.append(nxt)
                i += 2
                continue
            if ch == "'":
                in_single = False
            i += 1
            continue
        if ch == "'":
            in_single = True
            out.append(ch)
            i += 1
            continue
        if ch == "-" and nxt == "-":
            i += 2
            while i < n and sql[i] != "\n":
                i += 1
            out.append("\n")
            continue
        if ch == "/" and nxt == "*":
            i += 2
            while i + 1 < n and not (sql[i] == "*" and sql[i + 1] == "/"):
                i += 1
            i = i + 2 if i + 1 < n else n
            out.append(" ")
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _mask_literals(sql: str) -> str:
    masked = re.sub(r"'(?:''|[^'])*'", "''", sql)
    return re.sub(r'"(?:[^"]*)"', '""', masked)


def leading_keyword(sql: str) -> str:
    cleaned = remove_comments(sql).strip()
    match = re.match(r"([A-Za-z_]+)", cleaned)
    return match.group(1).lower() if match else ""


def guard_sql(sql: str) -> tuple[bool, str]:
    if not sql or not sql.strip():
        return False, "还没有可执行的 SQL。"
    if len(sql) > 20000:
        return False, "SQL 太长了。请控制在两万个字符以内。"
    if "；" in sql:
        return False, "你用了中文分号；。SQL 里请使用英文分号 ; 。"
    if "$" in sql:
        return False, "不能使用美元符号。美元引号会让语句检查失真，请改用普通单引号。"
    statements = [stmt for stmt in split_sql(sql) if remove_comments(stmt).strip()]
    if not statements:
        return False, "还没有可执行的 SQL。"
    for stmt in statements:
        code = remove_comments(stmt).strip()
        # 先扫原文。单引号遮盖会把美元引号里的函数名一起抹掉，检查就失效了。
        for pattern, message in _BANNED:
            if pattern.search(stmt) or pattern.search(code):
                return False, message
        masked = _mask_literals(code)
        for pattern, message in _BANNED:
            if pattern.search(masked):
                return False, message
        head = leading_keyword(stmt)
        if head in QUERY_HEADS:
            continue
        if head == "create":
            match = _CREATE_RE.match(masked.strip())
            if not match:
                return False, "建表只允许 CREATE TABLE 表名 AS SELECT。请不要建视图、宏或带模式名前缀的表。"
            name = match.group(1).lower()
            if name.startswith(PROTECTED_PREFIXES):
                return False, f"不能覆盖贴源表或维度表 {name}。请把结果写入题目指定的目标表。"
            continue
        if head == "drop":
            match = _DROP_RE.match(masked.strip())
            if not match:
                return False, "只允许 DROP TABLE 你自己生成的结果表。"
            name = match.group(1).lower()
            if name.startswith(PROTECTED_PREFIXES):
                return False, f"不能删除贴源表或维度表 {name}。要恢复初始订单，请使用「重置模拟数据」。"
            continue
    return True, ""


def quote_ident(name: str) -> str:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        raise ValueError(f"非法表名: {name}")
    return '"' + name.replace('"', "") + '"'
