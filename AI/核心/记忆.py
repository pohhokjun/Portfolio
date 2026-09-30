"""长期记忆：业务方纠正过的格式、口径、称呼这类「下次还用得上」的，agent 调 remember 记下，
存 记忆/<业务>/学到的.md，每单随人设一起给模型，下一单就生效。

不会越写越长：原文去重；超 上限 条就让大脑压成 压到 条，压缩失败就只留最新的。
"""
import time

import 环境

文件 = 环境.记忆 / "学到的.md"
上限, 压到 = 40, 25


def 读() -> list[str]:
    return [l[2:] for l in 文件.read_text(encoding="utf-8").splitlines() if l.startswith("- ")] if 文件.exists() else []


def _写(条: list[str]):
    文件.write_text("".join(f"- {x}\n" for x in 条), encoding="utf-8")


async def 记住(内容: str) -> str:
    内容 = " ".join(内容.split())
    if not 内容:
        raise ValueError("内容是空的")
    条 = 读()
    if any(内容 in x.split(" ", 1)[-1] or x.split(" ", 1)[-1] in 内容 for x in 条):
        return "已经记过了"
    条.append(f"{time.strftime('%m-%d')} {内容}")
    if len(条) > 上限:
        条 = await _压(条)
    _写(条)
    return f"记住了（共 {len(条)} 条）"


async def _压(条: list[str]) -> list[str]:
    from 核心 import 大脑
    try:
        答 = await 大脑.问一句(f"下面是业务方的长期要求，合并重复、删过时的，压到 {压到} 条以内，一行一条，以「- 」开头，别的不要写：\n"
                            + "\n".join(条))
        新 = [l[2:].strip() for l in 答.splitlines() if l.startswith("- ")]
        if 0 < len(新) <= 压到:
            return 新
    except Exception:
        pass
    return 条[-压到:]


def 给人设() -> str:
    条 = 读()
    return "【业务方的长期要求（学到的，优先遵守）】\n" + "\n".join(f"- {x}" for x in 条) if 条 else ""
