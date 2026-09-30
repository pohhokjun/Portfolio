# -*- coding: utf-8 -*-
"""
AutomationExercise 的假接口：商品 + 用户。框架骨架在 tools/mock_server.py，这里只放这个站的路由。

用法：pytest -m api --mock（site.yaml 的 mock 指向这里）
"""

from tools.mock_server import MockRoutes

# ---------------------------------------------------------------
# 假数据
#   商品字段和价格格式必须和真站点一致 —— 否则契约测试和落库校验
#   在 mock 上通过、在真站点上失败，mock 就成了自欺欺人。
# ---------------------------------------------------------------
_PRODUCTS = [
    (1, "Blue Top", "Rs. 500", "Polo", "Tops", "Women"),
    (2, "Men Tshirt", "Rs. 400", "H&M", "Tshirts", "Men"),
    (3, "Sleeveless Dress", "Rs. 1000", "Madame", "Dress", "Women"),
    (4, "Stylish Dress", "Rs. 1500", "Madame", "Dress", "Women"),
    (5, "Winter Top", "Rs. 600", "Madame", "Tops", "Women"),
    (6, "Summer White Top", "Rs. 400", "Madame", "Tops", "Women"),
    (7, "Fancy Green Top", "Rs. 700", "Mast & Harbour", "Tops", "Women"),
    (8, "Madame Top For Women", "Rs. 1000", "Madame", "Tops", "Women"),
    (9, "Pure Cotton V-Neck T-Shirt", "Rs. 1200", "Babyhug", "Tshirts", "Men"),
    (10, "Soft Stretch Jeans", "Rs. 1500", "Biba", "Jeans", "Women"),
    (11, "Regular Fit Straight Jeans", "Rs. 1500", "Kookie Kids", "Jeans", "Men"),
    (12, "Grunt Blue Slim Fit Jeans", "Rs. 1400", "Allen Solly Junior", "Jeans", "Kids"),
]

_BRANDS = ["Polo", "H&M", "Madame", "Mast & Harbour", "Babyhug",
           "Allen Solly Junior", "Kookie Kids", "Biba"]


_MISSING_LOGIN = ("Bad request, email or password parameter is missing "
                  "in POST request.")


def _product(row):
    pid, name, price, brand, cat, usertype = row
    return {"id": pid, "name": name, "price": price, "brand": brand,
            "category": {"category": cat, "usertype": {"usertype": usertype}}}


class Routes(MockRoutes):

    @staticmethod
    def init_server(srv):
        srv.users = {}

    # ---- 商品接口 --------------------------------------------
    def _h_productsList(self, method, query, body):
        if method != "GET":
            return self._biz(405, message="This request method is not supported.")
        self._biz(200, products=[_product(r) for r in _PRODUCTS])

    def _h_brandsList(self, method, query, body):
        if method != "GET":
            return self._biz(405, message="This request method is not supported.")
        self._biz(200, brands=[{"id": i + 1, "brand": b}
                               for i, b in enumerate(_BRANDS)])

    def _h_searchProduct(self, method, query, body):
        if method != "POST":
            return self._biz(405, message="This request method is not supported.")
        if "search_product" not in body:
            return self._biz(400, message="Bad request, search_product parameter "
                                          "is missing in POST request.")
        kw = str(body["search_product"]).strip().lower()
        # 空关键词真站点也返回 200 + 空列表，不是 400，照抄这个行为
        hits = [_product(r) for r in _PRODUCTS
                if kw and (kw in r[1].lower() or kw in r[4].lower())]
        self._biz(200, products=hits)

    # ---- 用户接口 --------------------------------------------
    def _h_verifyLogin(self, method, query, body):
        if method == "DELETE":
            return self._biz(405, message="This request method is not supported.")
        if not body.get("email") or not body.get("password"):
            return self._biz(400, message=_MISSING_LOGIN)
        user = self.server.users.get(body["email"])
        if user and user["password"] == body["password"]:
            return self._biz(200, message="User exists!")
        self._biz(404, message="User not found!")

    def _h_createAccount(self, method, query, body):
        if method != "POST":
            return self._biz(405, message="This request method is not supported.")
        for field in ("name", "email", "password"):
            if not body.get(field):
                return self._biz(400, message="Bad request, %s parameter is "
                                              "missing in POST request." % field)
        if body["email"] in self.server.users:
            return self._biz(400, message="Email Address already exist!")
        self.server.users[body["email"]] = dict(body)
        self._biz(201, message="User created!")

    def _h_updateAccount(self, method, query, body):
        if method != "PUT":
            return self._biz(405, message="This request method is not supported.")
        user = self.server.users.get(body.get("email"))
        if not user:
            return self._biz(404, message="User not found!")
        user.update(body)
        self._biz(200, message="User updated!")

    def _h_deleteAccount(self, method, query, body):
        if method != "DELETE":
            return self._biz(405, message="This request method is not supported.")
        user = self.server.users.get(body.get("email"))
        if not user or user["password"] != body.get("password"):
            return self._biz(404, message="Account not found!")
        del self.server.users[body["email"]]
        self._biz(200, message="Account deleted!")

    def _h_getUserDetailByEmail(self, method, query, body):
        if method != "GET":
            return self._biz(405, message="This request method is not supported.")
        user = self.server.users.get(query.get("email"))
        if not user:
            return self._biz(404, message="Account not found!")
        # 注意字段名：注册传的是 firstname，查询返回的是 first_name。
        # 真站点就是这么不一致的，mock 必须跟着不一致，
        # 否则用例在 mock 上过、在真站点上挂。
        self._biz(200, user={
            "id": abs(hash(user["email"])) % 100000,
            "name": user.get("name", ""),
            "email": user["email"],
            "first_name": user.get("firstname", ""),
            "last_name": user.get("lastname", ""),
            "city": user.get("city", ""),
            "country": user.get("country", ""),
        })
