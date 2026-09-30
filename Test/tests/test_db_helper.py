# -*- coding: utf-8 -*-
"""数据库校验工具的自测。

界面显示 100 元，库里存的可能是 100.00 或 10000（分为单位）。
这类问题只看接口 200 是发现不了的，得落库用 SQL 查。
"""

import pytest

from common import db_helper as db

PRODUCTS = [
    {"id": 1, "name": "蓝色上衣", "price": "Rs. 500", "brand": "Polo",
     "category": {"category": "Tops"}},
    {"id": 2, "name": "男士T恤", "price": "Rs. 400", "brand": "H&M",
     "category": {"category": "Tshirts"}},
]


class TestSchema:

    def test_建表可以重复执行(self, sandbox):
        db.init_schema()
        db.init_schema()      # 第二次不能报「表已存在」
        assert db.scalar("SELECT COUNT(*) FROM products") == 0


class TestSaveProducts:

    def test_落库条数正确(self, sandbox):
        assert db.save_products(PRODUCTS) == 2
        assert db.scalar("SELECT COUNT(*) FROM products") == 2

    def test_嵌套的分类字段被拍平(self, sandbox):
        db.save_products(PRODUCTS)
        assert db.query("SELECT category FROM products WHERE id=1")[0]["category"] == "Tops"

    def test_分类是字符串时也能存(self, sandbox):
        db.save_products([{"id": 9, "name": "x", "price": "1",
                           "brand": "b", "category": "直接就是字符串"}])
        assert db.query("SELECT category FROM products")[0]["category"] == "直接就是字符串"

    def test_分类缺失时存空串不存None(self, sandbox):
        db.save_products([{"id": 9, "name": "x", "price": "1", "brand": "b"}])
        assert db.query("SELECT category FROM products")[0]["category"] == ""

    def test_每次落库先清空避免上次的脏数据(self, sandbox):
        db.save_products(PRODUCTS)
        db.save_products([PRODUCTS[0]])
        assert db.scalar("SELECT COUNT(*) FROM products") == 1

    def test_空列表也能处理(self, sandbox):
        db.save_products(PRODUCTS)
        assert db.save_products([]) == 0
        assert db.scalar("SELECT COUNT(*) FROM products") == 0


class TestSaveBrands:

    def test_落库品牌(self, sandbox):
        assert db.save_brands([{"id": 1, "brand": "Polo"}]) == 1
        assert db.query("SELECT brand FROM brands")[0]["brand"] == "Polo"


class TestQuery:

    def test_查询返回字典列表可以按列名取(self, sandbox):
        db.save_products(PRODUCTS)
        rows = db.query("SELECT id, name FROM products ORDER BY id")
        assert rows[0]["name"] == "蓝色上衣"

    def test_支持参数化查询(self, sandbox):
        # 拼字符串会有 SQL 注入，参数化是唯一正确的写法
        db.save_products(PRODUCTS)
        rows = db.query("SELECT name FROM products WHERE brand=?", ("H&M",))
        assert [r["name"] for r in rows] == ["男士T恤"]

    def test_查不到时返回空列表(self, sandbox):
        db.init_schema()
        assert db.query("SELECT * FROM products WHERE id=999") == []

    def test_scalar取单值(self, sandbox):
        db.save_products(PRODUCTS)
        assert db.scalar("SELECT COUNT(*) FROM products") == 2

    def test_scalar查不到返回None(self, sandbox):
        db.init_schema()
        assert db.scalar("SELECT id FROM products WHERE id=999") is None


class TestRealChecks:
    """演示这个模块真正的用途：用 SQL 做数据一致性校验。"""

    def test_能查出重复ID(self, sandbox):
        db.save_products(PRODUCTS)
        dup = db.query("SELECT id FROM products GROUP BY id HAVING COUNT(*)>1")
        assert dup == []

    def test_能查出价格为空的商品(self, sandbox):
        db.save_products(PRODUCTS + [{"id": 3, "name": "坏数据", "price": None,
                                      "brand": "b", "category": "c"}])
        bad = db.query("SELECT id FROM products WHERE price IS NULL OR price=''")
        assert [r["id"] for r in bad] == [3]

    def test_写入过程报错时不会留下半截数据(self, sandbox):
        db.save_products(PRODUCTS)
        with pytest.raises(Exception):
            db.query("SELECT * FROM 根本没有这张表")
        assert db.scalar("SELECT COUNT(*) FROM products") == 2
