"""固定工作流（类似 Dify / n8n）：步骤写死在 业务/<名>/流程/*.json，按顺序跑，适合每次都一样的活。
Agent 适合开放的活；流程适合要稳定、可预期、每步可审计的活。两者可以混用：流程里的一步可以是 agent。

步骤类型（每步一个「名」，结果存进上下文，后面用 {名.字段} 引用；整串只有一个占位时保留原类型）：
  agent  ：跑一单，给「输出格式」(JSON schema) 就拿结构化结果
  函数   ：调 业务/<名>/工具.py 里的普通函数（纯代码校验、计算、落库）
  工具   ：调注册过的工具；高风险的要批准，前面已有审批步骤可写 "免批": true
  审批   ：等人批准，拒了流程停（写 "拒绝继续": true 就继续，后面用 条件 分支）
每步可选：条件（"确认.通过"，前面加 ! 取反）、重试（次数）。
并行组：{"名": "查", "并行": [步骤, 步骤…]} 组里同时跑、全完再往下；后面用 {子步名.字段} 或 {查.子步名.字段} 引用。
"""
import asyncio
import inspect
import re
import time

from 核心 import 业务, 大脑, 审批, 工具, 监控, 轨迹

_占 = re.compile(r"\{([^{}]+)\}")


def _取(上下文: dict, 路径: str):
    v = 上下文
    for k in 路径.strip().split("."):
        try:
            v = v[k] if isinstance(v, dict) else v[int(k)]
        except (KeyError, IndexError, ValueError, TypeError):
            raise ValueError(f"引用不到 {{{路径}}}：前面的步骤没产出「{k}」") from None
    return v


def 填(值, 上下文: dict):
    if isinstance(值, str):
        if m := _占.fullmatch(值.strip()):
            return _取(上下文, m[1])
        return _占.sub(lambda m: str(_取(上下文, m[1])), 值)
    if isinstance(值, dict):
        return {k: 填(v, 上下文) for k, v in 值.items()}
    if isinstance(值, list):
        return [填(v, 上下文) for v in 值]
    return 值


def 条件成立(式: str, 上下文: dict) -> bool:
    反 = 式.strip().startswith("!")
    return bool(_取(上下文, 式.strip().lstrip("!"))) != 反


async def _做(步: dict, 上下文: dict, 号: str, 来源: str, 单: dict):
    if "agent" in 步:
        r = await 大脑.跑一单(填(步["agent"], 上下文), 来源=f"流程:{号}", 输出格式=步.get("输出格式"))
        if r["出错"]:
            raise RuntimeError(r["出错"])
        单["交付"] += r["交付"]
        单["子单花费"] = 单.get("子单花费", 0) + r["花费"]
        return r["结构化"] if 步.get("输出格式") else {"回复": r["回复"], "交付": r["交付"], "编号": r["编号"]}
    if "函数" in 步:
        fn = getattr(业务.模块(), 步["函数"], None)
        if not fn:
            raise ValueError(f"业务 工具.py 里没有函数 {步['函数']}")
        出 = fn(**填(步.get("参数", {}), 上下文))
        return await 出 if inspect.isawaitable(出) else 出
    if "工具" in 步:
        项 = 工具.注册表.get(步["工具"])
        if not 项:
            raise ValueError(f"没有工具 {步['工具']}")
        参 = 填(步.get("参数", {}), 上下文)
        if 项["高风险"] and not 步.get("免批"):
            ok, 备注 = await 审批.请求(号, "批", f"{步['工具']} {参}")
            if not ok:
                raise RuntimeError(f"没批准 {步['工具']}：{备注}")
        if "单" in inspect.signature(项["fn"]).parameters:
            参["单"] = 单
        出 = 项["fn"](**参)
        return await 出 if inspect.isawaitable(出) else 出
    if "审批" in 步:
        ok, 备注 = await 审批.请求(号, "批", 填(步["审批"], 上下文))
        return {"通过": ok, "备注": 备注}
    raise ValueError(f"步骤 {步.get('名')} 没写类型（agent / 函数 / 工具 / 审批）")


async def _一步(步: dict, 上下文: dict, 号: str, 来源: str, 单: dict, 结果: dict) -> bool:
    """跑一步（或一个并行组），结果进上下文；返回 True = 审批被拒，流程停。"""
    步名, t0 = 步["名"], time.time()
    if "条件" in 步 and not 条件成立(步["条件"], 上下文):
        上下文[步名] = None
        结果["步骤"].append({"名": 步名, "状态": "跳过"})
        轨迹.记(号, "一轮", 动作=步名, 说明="条件不成立，跳过")
        return False
    if "并行" in 步:
        停 = await asyncio.gather(*[_一步(子, 上下文, 号, 来源, 单, 结果) for 子 in 步["并行"]])
        上下文[步名] = {子["名"]: 上下文.get(子["名"]) for 子 in 步["并行"]}
        return any(停)
    for 次 in range(步.get("重试", 0) + 1):
        try:
            出 = await _做(步, 上下文, 号, 来源, 单)
            break
        except Exception as e:
            轨迹.记(号, "步骤出错", 步=步名, 次=次 + 1, 出错=f"{type(e).__name__}: {e}")
            if 次 == 步.get("重试", 0):
                raise RuntimeError(f"「{步名}」失败：{e}") from None
    上下文[步名] = 出
    结果["步骤"].append({"名": 步名, "状态": "完成", "输出": 出, "用时": round(time.time() - t0, 1)})
    轨迹.记(号, "一轮", 动作=步名, 说明=str(出)[:200])
    if "审批" in 步 and not 出["通过"] and not 步.get("拒绝继续"):
        结果["停在"] = f"{步名}（没批准：{出['备注'] or '无理由'}）"
        return True
    return False


async def 跑(名: str, 输入: dict | None = None, 来源: str = "命令行", 号: str | None = None) -> dict:
    定义, 输入 = 业务.流程(名), 输入 or {}
    业务.模块()
    号 = 号 or 轨迹.下一号("F")
    起 = time.time()
    单 = {"编号": 号, "需求": f"流程 {名}", "来源": 来源, "会话": None, "交付": [], "工具": [], "开工": 起}
    结果 = {"编号": 号, "流程": 名, "步骤": [], "出错": None, "停在": None, "交付": 单["交付"]}
    上下文 = {"输入": 输入, **输入}
    轨迹.记(号, "开工", 需求=f"流程 {名}", 输入=输入, 来源=来源)
    try:
        if 缺 := [k for k in 定义.get("输入", []) if k not in 输入]:
            raise ValueError(f"缺输入：{'、'.join(缺)}")
        for 步 in 定义["步骤"]:
            if await _一步(步, 上下文, 号, 来源, 单, 结果):
                break
    except Exception as e:
        结果["出错"] = str(e)[:500]
    耗时 = round(time.time() - 起)
    轨迹.记(号, "崩" if 结果["出错"] else "收尾", 耗时=耗时, 出错=结果["出错"] or "", 原因=结果["停在"] or "")
    轨迹.存档(号, 需求=f"流程 {名} {输入}", 日期=time.strftime("%Y-%m-%d"), 时间=time.strftime("%H:%M:%S"), 来源=来源,
            结果="出错" if 结果["出错"] else "成", 出错=结果["出错"] or "", 耗时=耗时, 轮数=len(结果["步骤"]), 花费=0,
            交付=单["交付"], 回复=结果["停在"] or "", 流程=名, 步骤=结果["步骤"], 子单花费=round(单.get("子单花费", 0), 4),
            **审批.统计.pop(号, {}))   # 花费记 0：agent 步骤各自的单已经记过，别重复算进今日花费
    await 监控.单后检查({"编号": 号, "出错": 结果["出错"]})
    return 结果
