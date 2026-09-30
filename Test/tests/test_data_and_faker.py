# -*- coding: utf-8 -*-
"""测试数据读取 + 随机数据生成的自测。"""

import pytest

from common.data_reader import load_cases, load_json, load_yaml
from common.faker_util import PREFIX, random_email, random_password, random_string, random_user


class TestDataReader:

    def _write(self, sandbox, name, text):
        p = sandbox / "data" / name
        p.write_text(text, encoding="utf-8")
        return p

    def test_读yaml(self, sandbox):
        self._write(sandbox, "d.yaml", "a: 1\n")
        assert load_yaml("d.yaml") == {"a": 1}

    def test_文件不存在时报错信息要带上路径(self, sandbox):
        with pytest.raises(FileNotFoundError) as e:
            load_yaml("没有这个文件.yaml")
        assert "没有这个文件.yaml" in str(e.value)

    def test_空文件返回空字典而不是None(self, sandbox):
        # 返回 None 的话调用方一律要写 or {}，很容易漏
        self._write(sandbox, "empty.yaml", "")
        assert load_yaml("empty.yaml") == {}

    def test_读用例列表并生成可读的ID(self, sandbox):
        self._write(sandbox, "c.yaml",
                    "cases:\n  - title: 正常登录\n    a: 1\n  - id: TC02\n    a: 2\n")
        cases, ids = load_cases("c.yaml")
        assert len(cases) == 2
        assert ids == ["正常登录", "TC02"]

    def test_没有title和id时用序号兜底(self, sandbox):
        self._write(sandbox, "c.yaml", "cases:\n  - a: 1\n")
        assert load_cases("c.yaml")[1] == ["case_0"]

    def test_顶层直接是列表也能读(self, sandbox):
        self._write(sandbox, "c.yaml", "- title: 甲\n- title: 乙\n")
        assert load_cases("c.yaml")[1] == ["甲", "乙"]

    def test_自定义key(self, sandbox):
        self._write(sandbox, "c.yaml", "login:\n  - title: 甲\n")
        assert load_cases("c.yaml", key="login")[1] == ["甲"]

    def test_key不存在时返回空(self, sandbox):
        self._write(sandbox, "c.yaml", "cases:\n  - title: 甲\n")
        assert load_cases("c.yaml", key="没有这个key") == ([], [])

    def test_读json(self, sandbox):
        self._write(sandbox, "d.json", '{"a": 1}')
        assert load_json("d.json") == {"a": 1}


class TestFakerUtil:

    def test_随机串长度可控且只含小写和数字(self):
        s = random_string(10)
        assert len(s) == 10 and s.isalnum() and s.lower() == s

    def test_邮箱带统一前缀方便批量识别和清理(self):
        assert random_email().startswith(PREFIX + "_")

    def test_邮箱基本不重复(self):
        # 写死邮箱的话第二次跑就是「账号已存在」，用例不可重复执行。
        #
        # 这里为什么不写 == 200：随机串是 4 位 36 进制，约 168 万种，
        # 取 200 个按生日悖论算，撞一次的概率大概 1.2%。
        # 断言「一个都不许撞」就等于给自己埋了一条百次跑一次红的偶发用例 ——
        # 自动化里最讨厌的就是这种。要断言的是「够用」，不是「理论完美」。
        assert len({random_email() for _ in range(200)}) >= 198

    def test_密码符合常见强度要求(self):
        pwd = random_password()
        assert len(pwd) >= 8
        assert any(c.isupper() for c in pwd)
        assert any(c.isdigit() or c.islower() for c in pwd)
        assert "@" in pwd

    def test_注册用户字段齐全(self):
        # 少一个字段接口就会返回 400，而且报错信息通常很含糊
        need = {"name", "email", "password", "title", "birth_date", "birth_month",
                "birth_year", "firstname", "lastname", "company", "address1",
                "address2", "country", "zipcode", "state", "city", "mobile_number"}
        assert need <= set(random_user())

    def test_两次生成的用户不一样(self):
        assert random_user()["email"] != random_user()["email"]

    def test_出生日期在合法范围内(self):
        for _ in range(50):
            u = random_user()
            assert 1 <= int(u["birth_date"]) <= 28      # 避开 2 月 30 号这种坑
            assert 1980 <= int(u["birth_year"]) <= 2000

    def test_国家用站点接受的固定值(self):
        assert random_user()["country"] == "India"
