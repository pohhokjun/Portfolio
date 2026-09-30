"""示例业务的工具。新业务照这个写：@工具 注册，能用代码查的规矩在这查，不合格 raise 退回("原因")。"""
import time
from pathlib import Path

import pandas as pd

import 环境
from 核心.工具 import 工具, 退回

数据 = 环境.业务 / "数据"


def _找(path: str) -> Path:
    for p in (Path(path), 环境.工作区 / path, 数据 / path):
        if p.is_file():
            return p
    raise 退回(f"找不到 {path}。数据目录有：{', '.join(x.name for x in 数据.glob('*'))}")


@工具("table_info", "看 Excel/CSV 的结构：各 sheet 的列名、类型、行数、前 5 行、数值列统计。分析前先看这个。", {"path": str})
def 看表(path: str):
    p = _找(path)
    表 = pd.read_excel(p, sheet_name=None) if p.suffix in (".xlsx", ".xls") else {"csv": pd.read_csv(p)}
    return {名: {"行数": len(df), "列": {c: str(t) for c, t in df.dtypes.items()},
                "前5行": df.head().to_dict("records"), "数值统计": df.describe().round(2).to_dict()}
            for 名, df in 表.items()}


@工具("notify_boss", "把结论发给老板。会先等人批准。text 控制在 200 字内，先写结论。", {"text": str}, 高风险=True)
def 通知老板(text: str):
    if len(text) > 200:
        raise 退回("超过 200 字，老板不看长消息，压到结论。")
    # 示例里只落日志；真业务换成发邮件/企业微信/TG
    with (环境.工作区 / "已发通知.log").open("a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M')} {text}\n")
    return "已发给老板"


# 这些命令要先等人批准（正则，匹配 Bash/PowerShell 命令）
需批准命令 = [r"\bsend_mail\b", r"\bInvoke-RestMethod\b.*-Method\s+Post"]


def 数值检查(销售额: float, 订单数: int, 客单价: float) -> dict:
    """流程「月报」的代码校验步骤：数对不上就抛错，流程停在这，不会拿错数去问人。"""
    if 订单数 <= 0 or 销售额 <= 0:
        raise ValueError(f"销售额 {销售额} / 订单数 {订单数} 不合理")
    if abs(销售额 / 订单数 - 客单价) > 0.01:
        raise ValueError(f"客单价 {客单价} ≠ 销售额/订单数 {销售额 / 订单数:.2f}")
    return {"通过": True}


def 收尾检查(单):
    """想结束时框架会调它：返回原因就拦一次让模型补，None 放行。"""
    if 单.get("输出格式") or 单["来源"].startswith("流程"):   # 结构化结果直接给程序，不用 deliver
        return None
    if not 单["交付"]:
        return "对方什么都没收到：你直接打的字不会发出去。做完了就调 mcp__biz__deliver；确实不用交付就直接结束。"
    return None
