"""总入口。
python Work.py "需求" [@文件 …]  跑一单（审批/提问在终端里答）；@ 开头的是附件，图片模型直接看
python Work.py               交互模式，一句一单；输入「接着」续上一单的对话
python Work.py 服务           网页 API + 看板（http://127.0.0.1:8780）+ TG（配了才开）+ 定时，Ctrl+C 停
python Work.py 评测 [名字]    跑 业务/<名>/评测.jsonl，报告写 记忆/<业务>/评测报告.json
python Work.py 评测 对比 v1,v2 [名字]  同一套用例分别用两个人设版本跑，出对比表（A/B）
python Work.py 流程 [名 k=v]  不带名字列出流程；带就跑，如 流程 月报 月份=9
python Work.py mcp            把这个业务开放成 MCP 服务（stdio），给 Claude Code / Desktop 用
python Work.py 知识 [问题]    重建知识库，带问题就顺便查一下
python Work.py 检查           看配置：大脑、CLI、业务工具、团队、知识库
python Work.py 用户 [加 名字 权限1,权限2 [每日上限] | 删 名字]   管 API 用户和令牌（权限：派活 流程 批准 查看 管理）
换业务 set BIZ=名字；换大脑 set BRAIN=api / 兼容，见 环境.py。
"""
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.stdout.reconfigure(encoding="utf-8")

import 环境
from 核心 import 业务, 大脑, 审批, 工具, 知识库


def 打印(r):
    if r["出错"]:
        print(f"[{r['编号']}] 挂了：{r['出错']}")
    print(f"[{r['编号']}] {r.get('大脑')} {r.get('模型', '')} · {r['轮数']} 轮 · ${r['花费']:.4f}")
    for d in r["交付"]:
        print(d["文本"], *[f"\n  📎 {f}" for f in d["文件"]])
    if not r["交付"] and r["回复"]:
        print(r["回复"])


async def 交互():
    上次 = None
    while True:
        try:
            话 = input("\n需求（回车退出）> ").strip()
        except (EOFError, KeyboardInterrupt):
            return
        if not 话:
            return
        会话 = 上次 if 话 == "接着" and 上次 else f"终端{time.time():.0f}"
        if 话 == "接着":
            话 = input("接着做什么> ").strip()
        r = await 大脑.跑一单(话, 会话=会话)
        打印(r)
        上次 = 会话


async def 服务():
    from 通道 import 电报, 网页
    from 核心 import 调度
    审批.终端 = False
    await 调度.开()
    print(f"服务起来了：http://127.0.0.1:{环境.HTTP端口}  业务={环境.业务名} 大脑={环境.大脑}"
          + ("  TG=开" if 环境.TG["令牌"] else "  TG=没配"))
    await asyncio.gather(网页.开(), 电报.开())


def 检查():
    业务.模块()
    团 = 业务.团队() or {}
    行 = [("业务", f"{环境.业务名}  {环境.业务}"), ("工作区", 环境.工作区), ("大脑", f"{环境.大脑}  备用 {环境.备用大脑 or '无'}"),
         ("本机 CLI", f"{环境.CLI} {'有' if 环境.CLI.exists() else '没有（会用 SDK 自带的）'}"), ("模型", 环境.模型),
         ("API Key", "有" if __import__("os").environ.get("ANTHROPIC_API_KEY") else "没设（大脑=api 才要）"),
         ("兼容接口", f"{环境.兼容['地址']} {环境.兼容['模型']} {'有 Key' if 环境.兼容['密钥'] else '没 Key'}"),
         ("工具", ", ".join(f"{n}{'(要批准)' if x['高风险'] else ''}" for n, x in 工具.注册表.items())),
         ("团队", ", ".join(f"{k}：{v.description}" for k, v in 团.items()) or "无"),
         ("外部 MCP", ", ".join(业务.外部mcp()) or "无"), ("流程", ", ".join(业务.流程()) or "无"),
         ("人设", f"{业务.人设版本()}（可选：{', '.join(['v1'] + [f.stem.split('.')[1] for f in 环境.业务.glob('人设.v*.md')])}）"),
         ("需批准命令", 业务.需批准命令() or "无"), ("收尾检查", "有" if 业务.收尾检查() else "无"),
         ("知识库", f"{知识库.重建()} 块"), ("封顶", f"每单 {环境.档位['max_turns']} 轮 / ${环境.单笔上限}，每天 ${环境.每日上限}")]
    for k, v in 行:
        print(f"{k:　<6} {v}")


async def main(a):
    if not a:
        await 交互()
    elif a[0] == "服务":
        await 服务()
    elif a[0] == "评测" and len(a) > 2 and a[1] == "对比":
        from 核心 import 评测
        表 = await 评测.对比(a[2].split(","), a[3] if len(a) > 3 else "")
        print(f"{'版本':<6}{'通过':<8}{'平均轮数':<10}{'总花费':<10}平均耗时")
        for v, r in 表.items():
            print(f"{v:<6}{r['通过率']:<8}{r['平均轮数']:<10}{'$' + str(r['总花费']):<10}{r['平均耗时']}s")
    elif a[0] == "评测":
        from 核心 import 评测
        r = await 评测.跑(a[1] if len(a) > 1 else "")
        print(f"通过 {r['通过率']} · 平均 {r['平均轮数']} 轮 · 共 ${r['总花费']}")
    elif a[0] == "流程":
        if len(a) == 1:
            for 名, 说明 in 业务.流程().items():
                print(f"{名}：{说明}")
            return
        from 核心 import 流程
        输入 = {k: (int(v) if v.isdigit() else v) for k, v in (x.split("=", 1) for x in a[2:])}
        r = await 流程.跑(a[1], 输入)
        for s in r["步骤"]:
            print(f"- {s['名']} {s['状态']} {str(s.get('输出', ''))[:150]}")
        print(f"[{r['编号']}] " + (f"出错：{r['出错']}" if r["出错"] else f"停在 {r['停在']}" if r["停在"] else "完成"))
    elif a[0] == "mcp":
        from 核心.mcp出口 import server
        await server.run_stdio_async()
    elif a[0] == "知识":
        print(f"{知识库.重建()} 块")
        for x in 知识库.查(" ".join(a[1:])) if len(a) > 1 else []:
            print(f"- {x['出处']}  {x['文本'][:80]!r}")
    elif a[0] == "检查":
        检查()
    elif a[0] == "用户":
        from 核心 import 用户
        if len(a) >= 4 and a[1] == "加":
            print(f"{a[2]} 的令牌（只显示这一次）：{用户.加(a[2], a[3].split(','), float(a[4]) if len(a) > 4 else 0)}")
        elif len(a) == 3 and a[1] == "删":
            print("删了" if 用户.删(a[2]) else "没这个人")
        for u in 用户.列表():
            print(f"{u['名']}  {'、'.join(u['权限'])}  每日上限 {u['每日上限'] or '不限'}  令牌 {u['令牌']}")
        if 用户.开放模式():
            print("（没有用户、也没设 API_TOKEN：本机单人模式，API 不查令牌）")
    else:
        from 核心 import 附件
        文件 = [x[1:] for x in a if x.startswith("@") and Path(x[1:]).is_file()]
        路径 = [附件.存(Path(f).name, Path(f).read_bytes()) for f in 文件]
        打印(await 大脑.跑一单(" ".join(x for x in a if x[1:] not in 文件), 附件=路径))


def 清子进程():
    """停机时按父子关系杀自己的子孙（claude.exe、agent 后台起的脚本），只动自己起的，不按进程名杀。"""
    import psutil
    for p in psutil.Process().children(recursive=True):
        try:
            p.kill()
        except psutil.Error:
            pass


if __name__ == "__main__":
    try:
        asyncio.run(main(sys.argv[1:]))
    except KeyboardInterrupt:
        pass
    finally:
        清子进程()
