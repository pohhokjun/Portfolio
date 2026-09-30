# -*- coding: utf-8 -*-
"""
差异比对工具（文本 / 图像 / 字典）

【来源】从原 17_测试/core/diff.py 迁移，去掉了对旧 logger 的依赖。

用途：
    image_diff  UI 截图基线比对，检测非预期的界面变化
    dict_diff   接口响应结构比对，检测字段增删改
    text_diff   文本内容比对

为什么 pytest 生态里没有这个：
    pytest 只管「断言对不对」，不管「和上次比变没变」。
    视觉回归属于额外能力，通常要买商业工具（Applitools、Percy）。
    自己实现这一块是本项目的差异化亮点。
"""

import difflib
from pathlib import Path

from common.logger import get_logger

log = get_logger("diff")

try:
    from PIL import Image, ImageChops
    HAS_PIL = True
except Exception:
    HAS_PIL = False


# ---------------------------------------------------------------
# 文本比对
# ---------------------------------------------------------------
def text_diff(old, new, context=2):
    old_lines = (old or "").splitlines()
    new_lines = (new or "").splitlines()
    return list(difflib.unified_diff(old_lines, new_lines,
                                     "baseline", "current",
                                     n=context, lineterm=""))


def text_similarity(old, new):
    return round(difflib.SequenceMatcher(None, old or "", new or "").ratio(), 4)


# ---------------------------------------------------------------
# 图像比对
# ---------------------------------------------------------------
def _load(path):
    with Image.open(path) as img:
        return img.convert("RGB")


def image_diff(baseline_path, current_path, out_path=None,
               ignore_boxes=None, threshold=30):
    """
    逐像素比对两张图。

    参数：
        threshold      像素差异阈值，低于此值认为是渲染噪声，忽略
        ignore_boxes   要屏蔽的区域 [[x1,y1,x2,y2], ...]
                       用于遮住时间戳、轮播图、广告这类必然变化的区域

    返回：
        changed_ratio  变化像素占比，交给调用方和阈值比较
        diff_image     标红了差异区域的图片路径
    """
    if not HAS_PIL:
        return {"ok": None, "reason": "未安装 Pillow，跳过图像比对"}

    bp, cp = Path(baseline_path), Path(current_path)
    if not bp.exists() or not cp.exists():
        return {"ok": None, "reason": "基线或当前图不存在"}

    base = _load(bp)
    cur = _load(cp)

    # 尺寸不一致 = 页面高度变了 = 多半是真的布局回归，必须报出来。
    # 原来的写法是把当前图 resize 成基线尺寸再比 ——
    # 那等于把「页面少了一个模块」这种最该发现的问题拉伸掉了，
    # 而且拉伸本身会制造大片假差异，两头都不讨好。
    if base.size != cur.size:
        return {
            "ok": True,
            "changed_ratio": 1.0,
            "changed_pixels": cur.size[0] * cur.size[1],
            "total_pixels": base.size[0] * base.size[1],
            "diff_image": "",
            "size": list(cur.size),
            "size_mismatch": True,
            "reason": "尺寸不一致：基线 %dx%d，当前 %dx%d"
                      % (base.size[0], base.size[1], cur.size[0], cur.size[1]),
        }

    # 屏蔽动态区域
    if ignore_boxes:
        from PIL import ImageDraw
        for img in (base, cur):
            d = ImageDraw.Draw(img)
            for box in ignore_boxes:
                d.rectangle(tuple(box), fill=(0, 0, 0))

    delta = ImageChops.difference(base, cur).convert("L")
    hist = delta.histogram()
    total = base.size[0] * base.size[1]
    changed = sum(hist[threshold:])
    ratio = round(changed / float(total or 1), 6)

    # 生成差异图：把变化区域标红
    if out_path:
        try:
            mask = delta.point(lambda p: 255 if p >= threshold else 0)
            overlay = cur.copy()
            red = Image.new("RGB", cur.size, (255, 0, 0))
            overlay.paste(red, mask=mask)
            Path(out_path).parent.mkdir(parents=True, exist_ok=True)
            overlay.save(out_path)
        except Exception as exc:
            log.warning("差异图生成失败: %s", exc)
            out_path = None

    return {
        "ok": True,
        "changed_ratio": ratio,
        "changed_pixels": changed,
        "total_pixels": total,
        "diff_image": str(out_path) if out_path else "",
        "size": list(base.size),
    }


# ---------------------------------------------------------------
# 字典比对（接口响应结构）
# ---------------------------------------------------------------
def dict_diff(old, new, prefix=""):
    """递归比较两个字典，返回所有差异路径。"""
    out = []
    old = old or {}
    new = new or {}
    for key in sorted(set(old) | set(new)):
        p = "%s.%s" % (prefix, key) if prefix else str(key)
        a, b = old.get(key), new.get(key)
        if isinstance(a, dict) and isinstance(b, dict):
            out.extend(dict_diff(a, b, p))
        elif a != b:
            out.append({"path": p, "baseline": a, "current": b})
    return out
