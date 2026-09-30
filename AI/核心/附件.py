"""附件与图片多模态。

各通道收到的文件（API base64、看板上传、TG 图片/文件、命令行 @路径）都存进 工作区/收件/，路径随需求一起给模型。
图片（png/jpg/gif/webp，单张 ≤5MB）还会直接作为图片内容放进提问，模型当场就能看（截图、票据、报表照片、图表）；
其他文件模型自己用 Read/Python 打开。做的过程中模型也能随时 Read 图片文件看图，产出的图片用 deliver 交付。
"""
import base64
import re
import time
from pathlib import Path

import 环境

图片类型 = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif", ".webp": "image/webp"}
单图上限 = 5 * 1024 * 1024
总上限 = 20 * 1024 * 1024
收件 = 环境.工作区 / "收件"


def 存(名: str, 数据: bytes) -> str:
    d = 收件 / time.strftime("%Y%m%d_%H%M%S")
    d.mkdir(parents=True, exist_ok=True)
    p = d / (re.sub(r'[\\/:*?"<>|\s]+', "_", Path(名).name) or "附件")
    p.write_bytes(数据)
    return str(p)


def 存base64(列表: list) -> list[str]:
    """API / 看板传来的 [{"名"/"name", "数据"/"data": base64 或 data:URL}] → 存盘路径。不合格抛 ValueError。"""
    出, 总 = [], 0
    for x in 列表 or []:
        名, 数据 = x.get("名") or x.get("name") or "附件", x.get("数据") or x.get("data") or ""
        try:
            字节 = base64.b64decode(数据.split(",", 1)[-1] if 数据.startswith("data:") else 数据, validate=True)
        except Exception:
            raise ValueError(f"附件 {名} 不是合法的 base64") from None
        总 += len(字节)
        if 总 > 总上限:
            raise ValueError(f"附件合计超过 {总上限 // 1024 // 1024}MB")
        出.append(存(名, 字节))
    return 出


def 是图(p: str) -> bool:
    return Path(p).suffix.lower() in 图片类型


def 提问(需求: str, 附件: list[str]):
    """→ 纯文字（没附件）或 SDK 的流式输入（带图片内容块）。每次调用都新造，重试时能再用。"""
    if not 附件:
        return 需求
    文 = 需求 + "\n\n【附件】已存在工作区，图片你能直接看到，别的文件用 Read / Python 打开：\n" + "\n".join(f"- {p}" for p in 附件)
    图 = [p for p in 附件 if 是图(p) and Path(p).stat().st_size <= 单图上限]
    if not 图:
        return 文
    块 = [{"type": "text", "text": 文}] + [
        {"type": "image", "source": {"type": "base64", "media_type": 图片类型[Path(p).suffix.lower()],
                                     "data": base64.b64encode(Path(p).read_bytes()).decode()}} for p in 图]

    async def 流():
        yield {"type": "user", "message": {"role": "user", "content": 块}}
    return 流()
