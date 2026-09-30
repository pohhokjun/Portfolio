# -*- coding: utf-8 -*-
"""购物车页元素定位"""


class CartLoc:
    CART_TABLE = '#cart_info_table'
    CART_ROWS = '#cart_info_table tbody tr'
    EMPTY_CART = '#empty_cart'

    PRODUCT_NAME = 'td.cart_description h4 a'
    PRODUCT_PRICE = 'td.cart_price p'
    PRODUCT_QUANTITY = 'td.cart_quantity button'
    PRODUCT_TOTAL = 'td.cart_total p'
    DELETE_BUTTON = 'a.cart_quantity_delete'

    PROCEED_TO_CHECKOUT = 'a:has-text("Proceed To Checkout")'
