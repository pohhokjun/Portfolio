# -*- coding: utf-8 -*-
"""商品列表页元素定位"""


class ProductsLoc:
    SEARCH_INPUT = '#search_product'
    SEARCH_BUTTON = '#submit_search'

    ALL_PRODUCTS_TITLE = 'h2:has-text("All Products")'
    SEARCHED_TITLE = 'h2:has-text("Searched Products")'

    PRODUCT_CARDS = '.features_items .product-image-wrapper'
    PRODUCT_NAMES = '.features_items .productinfo p'
    PRODUCT_PRICES = '.features_items .productinfo h2'

    # 加入购物车按钮（全部），取第几个由 Playwright 的 .nth() 决定
    #
    # ★ 这里踩过一个很典型的坑，面试可以讲 ★
    #   原来写的是 '.product-image-wrapper:nth-child(%d) ... .add-to-cart'，
    #   想用 :nth-child(2) 拿第 2 个商品。结果永远拿不到。
    #   原因：:nth-child 数的是「在自己父节点里排第几」，不是「同类元素里排第几」。
    #   这个站的 DOM 是 <div class="col-sm-4"><div class="product-image-wrapper">…，
    #   每个 wrapper 都是父节点唯一的孩子，所以 :nth-child(1) 匹配全部 34 个，
    #   :nth-child(2) 匹配 0 个。
    #   正确做法：用 CSS 选一组元素，再用 Playwright 的 .nth(i) 按顺序取。
    ADD_TO_CART_ALL = '.features_items .productinfo .add-to-cart'

    # 加购后的弹窗
    CART_MODAL = '#cartModal'
    MODAL_VIEW_CART = '#cartModal a[href="/view_cart"]'
    MODAL_CONTINUE = '#cartModal button:has-text("Continue Shopping")'
