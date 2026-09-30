# -*- coding: utf-8 -*-
"""这个站的 fixture。第一行把 cfg 绑到本站，目录下所有用例拿到的都是本站配置。"""

from plugins.site_plugin import site_cfg

cfg = site_cfg("_模板")   # ← 改成文件夹名
