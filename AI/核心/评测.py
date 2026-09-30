"""评测：业务/<名>/评测.jsonl 每行一个用例，真跑 agent，按规则 + 可选大模型评审打分。
换大脑、改人设、加工具后跑一遍，对比 记忆/<业务>/评测报告.json。

用例字段（都可选，只有 需求 必填）：
  名、需求、包含[回复里必须有]、不含[不能有]、文件[工作区里要新生成的 glob]、工具[必须调过的]、
  最多轮、批准（遇到审批自动 true/false，默认 false）、回答（遇到 ask_human 自动答什么）、评审（给大模型的判分标准）
"""
import json
import time

import 环境
from 核心 import 大脑, 审批, 定时, 记忆, 轨迹


def 读用例() -> list[dict]:
    f = 环境.业务 / "评测.jsonl"
    return [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()] if f.exists() else []


async def 判(例: dict, r: dict, 起: float) -> list[str]:
    """→ 没过的项（空 = 通过）"""
    文 = r["回复"] + "\n" + "\n".join(d["文本"] for d in r["交付"])
    错 = []
    if r["出错"]:
        错.append(f"出错：{r['出错']}")
    错 += [f"缺「{x}」" for x in 例.get("包含", []) if x not in 文]
    错 += [f"不该有「{x}」" for x in 例.get("不含", []) if x in 文]
    for g in 例.get("文件", []):
        if not any(p.stat().st_mtime >= 起 for p in 环境.工作区.glob(g)):
            错.append(f"没生成 {g}")
    错 += [f"没调 {t}" for t in 例.get("工具", []) if not any(t == x or x.endswith("__" + t) for x in r["工具"])]
    if (n := 例.get("最多轮")) and r["轮数"] > n:
        错.append(f"轮数 {r['轮数']} > {n}")
    if 例.get("评审") and not r["出错"]:
        答 = await 大脑.问一句(f"判分标准：{例['评审']}\n\n需求：{例['需求']}\n\n交付内容：{文[:4000]}\n\n"
                           "符合标准回「通过」，否则回「不通过：原因」。只回这一行。")
        if not 答.strip().startswith("通过"):
            错.append(f"评审：{答.strip()[:200]}")
    return 错


async def _记(例, r, 起) -> dict:
    错 = await 判(例, r, 起)
    x = {"名": 例.get("名", 例["需求"][:20]), "编号": r["编号"], "通过": not 错, "没过": 错,
         "轮数": r["轮数"], "花费": round(r["花费"], 4), "耗时": round(time.time() - 起)}
    print(f"{'✓' if not 错 else '✗'} {x['名']}  {r['轮数']} 轮 ${r['花费']:.3f}  {'；'.join(错)}")
    return x


async def 对比(版本: list[str], 只跑: str = "") -> dict:
    """A/B：同一套用例每个人设版本各跑一遍，报告存 评测对比.json。"""
    from 核心 import 业务
    表 = {}
    try:
        for v in 版本:
            业务.人设版本覆盖 = v
            print(f"── 人设 {v} ──")
            表[v] = await 跑(只跑)
    finally:
        业务.人设版本覆盖 = None
    (环境.记忆 / "评测对比.json").write_text(json.dumps(表, ensure_ascii=False, indent=1), encoding="utf-8")
    return 表


async def 跑(只跑: str = "") -> dict:
    """每个用例都从同一起点跑：学到的记忆先清空、跑完恢复；用例里建的定时任务跑完删掉，别到点真去做。"""
    明细 = []
    原记忆 = 记忆.文件.read_text(encoding="utf-8") if 记忆.文件.exists() else None
    try:
        for 例 in [x for x in 读用例() if not 只跑 or 只跑 in x.get("名", "")]:   # 故意串行：每例清空/恢复记忆，并行会互相污染
            记忆.文件.unlink(missing_ok=True)
            原定时 = {x["id"] for x in 定时.列表()}
            审批.自动 = {"批": 例.get("批准", False), "答": 例.get("回答", "")}
            起 = time.time() - 1
            r = await 大脑.跑一单(例["需求"], 来源="评测", 编号=轨迹.下一号("E"))
            for x in 定时.列表():
                if x["id"] not in 原定时:
                    定时.删(x["id"])
            明细.append(await _记(例, r, 起))
    finally:
        审批.自动 = None
        记忆.文件.unlink(missing_ok=True)
        if 原记忆 is not None:
            记忆.文件.write_text(原记忆, encoding="utf-8")
    n = len(明细) or 1
    from 核心 import 业务
    报告 = {"时间": time.strftime("%Y-%m-%d %H:%M:%S"), "业务": 环境.业务名, "大脑": 环境.大脑, "人设": 业务.人设版本(),
          "通过率": f"{sum(x['通过'] for x in 明细)}/{len(明细)}", "平均轮数": round(sum(x["轮数"] for x in 明细) / n, 1),
          "总花费": round(sum(x["花费"] for x in 明细), 4), "平均耗时": round(sum(x["耗时"] for x in 明细) / n), "明细": 明细}
    (环境.记忆 / "评测报告.json").write_text(json.dumps(报告, ensure_ascii=False, indent=1), encoding="utf-8")
    return 报告
