# -*- coding: utf-8 -*-
"""
日志模块

为什么要有日志：
    测试失败时，报告只告诉你「失败了」，日志告诉你「失败前发生了什么」。
    面试问「你怎么定位自动化用例的偶发失败」，答案就是日志 + 截图 + 录屏。

★ 这里踩过一个很隐蔽的坑，值得记下来 ★
    之前的写法是：在名为 "qa" 的 logger 上挂 handler，
    但 get_logger("api") 返回的是 logging.getLogger("api")。
    "api" 和 "qa" 在 logging 的树里是两棵不相干的分支 ——
    "api" 的父节点是 root，不是 "qa"。
    结果：handler 一个都没生效，日志文件全程 0 字节，谁也没发现。

    正确做法：所有子 logger 都必须挂在同一个命名空间下，
    即 logging.getLogger("qa." + name)，靠名字里的点号建立父子关系。

    propagate 保持 True，日志才能同时进 pytest 的 log_file（reports/logs/pytest.log）。
    重复输出的问题不存在：pytest 默认不加控制台 handler（log_cli=false）。
"""

import logging
import sys
import threading
from datetime import datetime

from config.settings import LOG_DIR

ROOT_NAME = "qa"

_lock = threading.Lock()
_configured = False


def use_utf8_console():
    """
    让控制台能打中文。任何要往终端输出中文的入口都该先调一次。

    本项目的日志和命令行输出全是中文。Windows 上 Python 的 stdout
    默认跟系统代码页走（简体中文 cp936，英文区 cp1252），
    而且输出被重定向到文件或管道时也走同一套 —— 遇到中文直接
    UnicodeEncodeError。日志里表现为整条被吞掉，命令行里表现为直接崩掉：

        python -m tools.cli doctor        # 英文区 / 重定向输出时必崩

    Win10/11 的终端本身支持 UTF-8，把 stdout 切过去就正常了。
    errors="replace" 是最后一道保险 —— 显示成问号也比崩掉强。
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            if (getattr(stream, "encoding", "") or "").lower() not in ("utf-8", "utf8"):
                stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    return sys.stdout


def _configure():
    """给 qa 这个命名空间装一次 handler。多线程/多次调用都只装一次。"""
    global _configured
    with _lock:
        if _configured:
            return
        root = logging.getLogger(ROOT_NAME)
        root.setLevel(logging.DEBUG)
        root.handlers.clear()
        # 保持 True：日志继续上抛到 root，pytest 的 log_file 才收得到
        root.propagate = True

        fmt = logging.Formatter(
            "%(asctime)s | %(levelname)-7s | %(name)-18s | %(message)s",
            datefmt="%H:%M:%S",
        )

        # 控制台：只看 INFO 以上，避免刷屏
        console = logging.StreamHandler(use_utf8_console())
        console.setLevel(logging.INFO)
        console.setFormatter(fmt)
        root.addHandler(console)

        # 文件：记录 DEBUG 全量，排查问题用
        # xdist 并行时多个进程写同一个文件，Windows 上会互相锁；
        # delay=True 让文件到第一条日志才真正打开，减少空占用。
        logfile = LOG_DIR / ("run_%s.log" % datetime.now().strftime("%Y%m%d"))
        try:
            fh = logging.FileHandler(logfile, encoding="utf-8", delay=True)
            fh.setLevel(logging.DEBUG)
            fh.setFormatter(fmt)
            root.addHandler(fh)
        except OSError:
            # 日志文件写不了不该让整个测试跑不起来，控制台还在
            pass

        _configured = True


def get_logger(name="qa"):
    """
    取一个 logger。

    name 传 "api"、"page" 这类短名即可，
    内部统一挂到 qa.<name> 下，保证 handler 生效。
    """
    _configure()
    name = str(name or ROOT_NAME)
    if name == ROOT_NAME or name.startswith(ROOT_NAME + "."):
        return logging.getLogger(name)
    return logging.getLogger("%s.%s" % (ROOT_NAME, name))


log = get_logger()
