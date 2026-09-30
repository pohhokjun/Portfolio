# -*- coding: utf-8 -*-
"""登录/注册页元素定位"""


class LoginLoc:
    # 该站点贴心地给关键元素加了 data-qa 属性，专门给自动化用
    # 这类属性是最稳定的定位方式，优于 xpath 和 css class
    LOGIN_EMAIL = 'input[data-qa="login-email"]'
    LOGIN_PASSWORD = 'input[data-qa="login-password"]'
    LOGIN_BUTTON = 'button[data-qa="login-button"]'

    SIGNUP_NAME = 'input[data-qa="signup-name"]'
    SIGNUP_EMAIL = 'input[data-qa="signup-email"]'
    SIGNUP_BUTTON = 'button[data-qa="signup-button"]'

    # 提示文案
    LOGIN_FORM_TITLE = 'h2:has-text("Login to your account")'
    SIGNUP_FORM_TITLE = 'h2:has-text("New User Signup!")'
    LOGIN_ERROR = 'p:has-text("Your email or password is incorrect!")'
    SIGNUP_ERROR = 'p:has-text("Email Address already exist!")'
