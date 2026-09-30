"""语义缓存：几乎一样的只读问题直接给上次的答案，不再跑模型（省钱、秒回）。

只在调用方明确要（缓存=True，如 FAQ、口径问答）时查；只存「纯问答」的单：没交付文件、没人工介入、
没调高风险/有副作用的工具。相似度用去标点后的字/两字计数余弦 ≥ 阈值，且问题里的数字必须完全一样（「9月」≠「10月」）。
失效：超过业务配置的 缓存小时、人设版本变了、知识库改了。
"""
import json
import re
import time

import 环境
from 核心 import 业务, 知识库

文件 = 环境.记忆 / "缓存.json"
阈值 = 0.9
有副作用 = {"notify_boss", "schedule", "cancel_schedule", "remember", "ask_human", "browser_run"}


def _读() -> list:
    try:
        return json.loads(文件.read_text(encoding="utf-8"))
    except Exception:
        return []


def _版本() -> str:
    return f"{业务.人设版本()}|{知识库._指纹()}"


def 查(需求: str) -> dict | None:
    小时 = 业务.配置()["缓存小时"]
    if not 小时:
        return None
    现, 版 = time.time(), _版本()
    候选 = [x for x in _读() if 现 - x["时间"] < 小时 * 3600 and x["版本"] == 版
          and re.findall(r"\d+", x["需求"]) == re.findall(r"\d+", 需求)]
    if not 候选:
        return None
    from sklearn.feature_extraction.text import CountVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    # 去掉标点空白再按字/两字计数比：只有几句话时 TF-IDF 会把共有的字压低，反而不准
    文 = [re.sub(r"[\W_]+", "", x.lower()) for x in [需求] + [x["需求"] for x in 候选]]
    m = CountVectorizer(analyzer="char", ngram_range=(1, 2)).fit_transform(文)
    相似 = cosine_similarity(m[0], m[1:])[0]
    i = int(相似.argmax())
    return {**候选[i], "相似": round(float(相似[i]), 3)} if 相似[i] >= 阈值 else None


def 可存(r: dict) -> bool:
    return (not r.get("出错") and r.get("交付") and not any(d["文件"] for d in r["交付"])
            and not r.get("人工次数") and not (有副作用 & {t.split("__")[-1] for t in r.get("工具", [])}))


def 存(需求: str, r: dict):
    if not 业务.配置()["缓存小时"] or not 可存(r):
        return
    表 = [x for x in _读() if time.time() - x["时间"] < 业务.配置()["缓存小时"] * 3600][-500:]
    表.append({"需求": 需求, "交付": r["交付"], "回复": r["回复"], "来自": r["编号"], "时间": time.time(), "版本": _版本()})
    文件.write_text(json.dumps(表, ensure_ascii=False), encoding="utf-8")
