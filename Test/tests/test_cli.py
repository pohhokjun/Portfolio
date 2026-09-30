# -*- coding: utf-8 -*-
"""命令行工具的自测。

命令行是这个项目的另一个入口，
但它长期没人测 —— 直到发现 `python -m tools.cli doctor`
在英文区系统上第一行就崩。
入口崩了，后面做得再好也没人看得到。
"""

import sys

import pytest

from tools import cli
from common.logger import use_utf8_console


class TestTable:
    """中文对齐的表格输出。终端里宽度算错，表格就会歪成一团。"""

    def test_空数据有提示(self, capsys):
        cli.table(["a"], [])
        assert "无数据" in capsys.readouterr().out

    def test_中文按两个字符宽度算(self, capsys):
        cli.table(["名称", "值"], [["中文", "1"], ["ab", "22"]])
        lines = [l for l in capsys.readouterr().out.splitlines() if l.strip()]
        # 每一行的显示宽度要一致，表格才不会歪
        widths = {sum(2 if ord(c) > 0x2E80 else 1 for c in l) for l in lines}
        assert len(widths) == 1

    def test_None显示成空串不显示成None(self, capsys):
        cli.table(["a", "b"], [[None, "x"]])
        assert "None" not in capsys.readouterr().out


class TestParser:

    def test_不带子命令时打印帮助并正常退出(self, capsys):
        assert cli.main([]) == 0
        assert "usage" in capsys.readouterr().out.lower()

    @pytest.mark.parametrize("cmd", ["explore", "gen", "sitemap",
                                     "accounts", "cleanup", "doctor"])
    def test_每个子命令都挂上了处理函数(self, cmd):
        args = cli.build_parser().parse_args([cmd])
        assert callable(args.func)

    def test_baseline只剩list和clear(self):
        # prune 说的是「清理失效基线」，做的是「全删」，已经去掉了。
        # 名不副实的破坏性命令，早晚会误伤别人的基线。
        with pytest.raises(SystemExit):
            cli.build_parser().parse_args(["baseline", "prune"])
        for action in ("list", "clear"):
            assert cli.build_parser().parse_args(["baseline", action]).action == action

    def test_环境参数在子命令之前(self):
        assert cli.build_parser().parse_args(["--env", "prod", "doctor"]).env == "prod"

    def test_未知子命令直接报错(self):
        with pytest.raises(SystemExit):
            cli.build_parser().parse_args(["没有这个命令"])


class TestCommands:

    def test_doctor能跑通并列出检查项(self, capsys):
        assert cli.main(["doctor"]) == 0
        out = capsys.readouterr().out
        assert "环境自检" in out and "pytest" in out

    def test_站点地图不存在时给出下一步提示(self, capsys, monkeypatch, tmp_path):
        from tools import sitemap
        monkeypatch.setattr(sitemap, "ROOT", tmp_path)
        assert cli.main(["gen"]) == 2
        assert "请先执行" in capsys.readouterr().out

    def test_账号池没配账号时不报错只提示(self, capsys, sandbox):
        assert cli.main(["accounts"]) == 0
        assert "未配置账号" in capsys.readouterr().out

    def test_没有遗留数据时明确说没有(self, capsys, sandbox):
        assert cli.main(["cleanup"]) == 0
        assert "没有遗留数据" in capsys.readouterr().out


class TestConsoleEncoding:
    """
    ★ 回归用例：钉住命令行入口崩溃的 bug ★

    这个项目所有的命令行输出都是中文。
    Windows 上 Python 的 stdout 跟系统代码页走，输出被重定向时也一样，
    在英文区系统（cp1252）上 `python -m tools.cli doctor` 的第一个
    print 就是 UnicodeEncodeError，整个命令直接崩掉，
    连「环境自检」四个字都打不出来。
    """

    def test_把控制台切成UTF8(self):
        use_utf8_console()
        assert (sys.stdout.encoding or "").lower().replace("-", "") == "utf8"

    def test_stderr也要切(self):
        use_utf8_console()
        assert (sys.stderr.encoding or "").lower().replace("-", "") == "utf8"

    def test_流不支持reconfigure时不能抛异常(self, monkeypatch):
        class 假的流:
            encoding = "cp1252"

        monkeypatch.setattr(sys, "stdout", 假的流())
        use_utf8_console()      # 不抛异常即通过

    def test_中文输出不崩(self, capsys):
        cli.title("环境自检 · 中文标题")
        assert "环境自检" in capsys.readouterr().out
