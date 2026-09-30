# -*- coding: utf-8 -*-
"""
数据库校验工具（SQLite）

★ 这是本项目区别于普通作品集的地方 ★

普通自动化只验证「界面显示对不对」，
真实工作中还要验证「数据落库对不对」——
界面显示 100 元，数据库存的可能是 100.00 或 10000（分为单位）。

本模块把接口返回的数据落到本地 SQLite，然后用 SQL 做一致性校验，
演示「UI/接口 + 数据库」的端到端验证能力。

面试话术：
    「我在项目里加了数据库校验层。举个例子，商品列表接口返回 500 条，
     我落库后用 SQL 检查价格字段是否有空值、是否有重复 ID、
     分类数量是否和品牌接口对得上。这类问题光看接口 200 是发现不了的。」

不需要装 MySQL —— SQLite 是 Python 自带的，零安装成本。
"""

import sqlite3
from contextlib import contextmanager

from config.settings import DB_PATH
from common.logger import get_logger

log = get_logger("db")


@contextmanager
def connect():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row      # 让查询结果能按列名访问
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_schema():
    """建表。每次运行前调用，保证结构存在。"""
    with connect() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS products (
            id          INTEGER PRIMARY KEY,
            name        TEXT,
            price       TEXT,
            brand       TEXT,
            category    TEXT,
            captured_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS brands (
            id          INTEGER PRIMARY KEY,
            brand       TEXT
        );
        """)
    log.debug("数据库表结构已就绪: %s", DB_PATH)


def save_products(products):
    """把接口返回的商品列表写入数据库。"""
    init_schema()
    rows = []
    for p in products:
        cat = p.get("category") or {}
        rows.append((
            p.get("id"),
            p.get("name"),
            p.get("price"),
            p.get("brand"),
            (cat.get("category") if isinstance(cat, dict) else str(cat)) or "",
        ))
    with connect() as conn:
        conn.execute("DELETE FROM products")
        conn.executemany(
            "INSERT OR REPLACE INTO products (id,name,price,brand,category)"
            " VALUES (?,?,?,?,?)", rows)
    log.info("已落库商品 %d 条", len(rows))
    return len(rows)


def save_brands(brands):
    init_schema()
    rows = [(b.get("id"), b.get("brand")) for b in brands]
    with connect() as conn:
        conn.execute("DELETE FROM brands")
        conn.executemany("INSERT OR REPLACE INTO brands (id,brand) VALUES (?,?)", rows)
    return len(rows)


def query(sql, params=()):
    """执行查询，返回字典列表。"""
    with connect() as conn:
        cur = conn.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]


def scalar(sql, params=()):
    """返回单个值，用于 count 之类的查询。"""
    with connect() as conn:
        cur = conn.execute(sql, params)
        row = cur.fetchone()
        return row[0] if row else None
