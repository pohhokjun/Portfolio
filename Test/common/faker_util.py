# -*- coding: utf-8 -*-
"""
随机测试数据生成

为什么需要：
    注册类用例如果写死邮箱，第二次跑就会报「账号已存在」。
    这叫「用例不可重复执行」，是自动化的大忌。

    面试话术：自动化用例必须满足「幂等性」——
    要么用随机数据，要么执行完自动清理。本项目两种都做了。
"""

import random
import string
import time

from faker import Faker

fake = Faker()
PREFIX = "qa_auto"        # 统一前缀，方便识别和批量清理


def random_string(n=6):
    return "".join(random.choice(string.ascii_lowercase + string.digits)
                   for _ in range(n))


def random_email():
    """带时间戳 + 随机串，几乎不可能重复。"""
    return "%s_%s_%s@example.com" % (PREFIX, int(time.time()), random_string(4))


def random_password():
    return "Test@%s" % random_string(8)


def random_user():
    """生成一个完整的注册用户，字段对应 automationexercise 的 createAccount 接口。"""
    return {
        "name": "%s_%s" % (PREFIX, random_string(5)),
        "email": random_email(),
        "password": random_password(),
        "title": random.choice(["Mr", "Mrs"]),
        "birth_date": str(random.randint(1, 28)),
        "birth_month": random.choice(["January", "June", "December"]),
        "birth_year": str(random.randint(1980, 2000)),
        "firstname": fake.first_name(),
        "lastname": fake.last_name(),
        "company": "QA Portfolio",
        "address1": fake.street_address(),
        "address2": "",
        "country": "India",          # 该站点仅接受固定几个国家
        "zipcode": fake.postcode(),
        "state": fake.city(),
        "city": fake.city(),
        "mobile_number": "13800138000",
    }
