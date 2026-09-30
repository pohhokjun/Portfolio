# -*- coding: utf-8 -*-
"""
基线管理（视觉回归 + 接口结构回归）

【来源】从原 17_测试/core/baseline.py 迁移，改为读新的 config.settings。

★ 这是本项目区别于普通 pytest 作品集的核心能力之一 ★

解决的问题：
    普通断言只能验证「我知道要检查什么」。
    但页面改版时，很多变化你根本想不到要去断言 ——
    比如按钮颜色变了、间距乱了、某个模块消失了。

    基线比对反过来做：把上一次的样子存下来，
    这一次和上次不一样就告警。这叫「视觉回归测试」。

工作流程：
    第一次运行  -> 没有基线，自动建立，用例通过
    之后运行    -> 和基线比对，差异超阈值就失败
    确认是正常改版 -> 执行 baseline 更新，用新截图覆盖

面试话术：
    「pytest 本身没有视觉回归能力，商业方案是 Applitools、Percy。
      我自己实现了一套：Pillow 逐像素比对，支持屏蔽动态区域
      （时间戳、轮播图），差异超过阈值就失败并生成标红的差异图。」
"""

import json
import re
import shutil
from pathlib import Path

from config.settings import get_config, ROOT
from common import diff
from common.logger import get_logger

log = get_logger("baseline")


def safe_name(text):
    """把用例名转成安全的文件名。"""
    return re.sub(r"[^0-9A-Za-z_\-\u4e00-\u9fff]+", "_", str(text)).strip("_") or "x"


class BaselineStore:
    def __init__(self, cfg=None):
        self.cfg = cfg or get_config()
        self.dir = ROOT / "reports" / "baseline" / self.cfg.tag
        self.dir.mkdir(parents=True, exist_ok=True)

        vc = self.cfg.get("visual", {}) or {}
        self.threshold = float(vc.get("diff_threshold", 0.02))
        self.pixel_threshold = int(vc.get("pixel_threshold", 30))
        self.auto_create = bool(vc.get("auto_create", True))
        self.ignore_boxes = vc.get("ignore_boxes", {}) or {}

    # -----------------------------------------------------------
    # 路径管理
    # -----------------------------------------------------------
    def _key_dir(self, case_id):
        d = self.dir / safe_name(case_id)
        d.mkdir(parents=True, exist_ok=True)
        return d

    def image_path(self, case_id, name):
        return self._key_dir(case_id) / ("%s.png" % safe_name(name))

    def data_path(self, case_id, name):
        return self._key_dir(case_id) / ("%s.json" % safe_name(name))

    def has(self, case_id, name):
        return self.image_path(case_id, name).exists()

    # -----------------------------------------------------------
    # 图像基线
    # -----------------------------------------------------------
    def update_image(self, case_id, name, current_path):
        dst = self.image_path(case_id, name)
        shutil.copyfile(current_path, dst)
        log.info("基线已更新: %s/%s", case_id, name)
        return str(dst)

    def compare_image(self, case_id, name, current_path, out_dir=None):
        base = self.image_path(case_id, name)

        if not base.exists():
            if self.auto_create and current_path:
                self.update_image(case_id, name, current_path)
                return {"status": "created", "changed_ratio": 0.0,
                        "message": "首次运行，已建立基线"}
            return {"status": "missing", "changed_ratio": None,
                    "message": "缺少基线"}

        out_path = None
        if out_dir:
            out_path = Path(out_dir) / ("%s__%s__diff.png"
                                        % (safe_name(case_id), safe_name(name)))

        boxes = self.ignore_boxes.get(case_id) or self.ignore_boxes.get("*") or []
        res = diff.image_diff(str(base), str(current_path), out_path,
                              ignore_boxes=boxes, threshold=self.pixel_threshold)

        if res.get("ok") is None:
            return {"status": "skip", "changed_ratio": None,
                    "message": res.get("reason", "")}

        ratio = res["changed_ratio"]
        status = "same" if ratio <= self.threshold else "changed"
        if res.get("size_mismatch"):
            message = res.get("reason", "截图尺寸与基线不一致")
        elif status == "same":
            message = ""
        else:
            message = ("像素差异 %.4f%% 超过阈值 %.4f%%"
                       % (ratio * 100, self.threshold * 100))
        return {
            "status": status,
            "changed_ratio": ratio,
            "threshold": self.threshold,
            "diff_image": res.get("diff_image", ""),
            "baseline_image": str(base),
            "message": message,
        }

    # -----------------------------------------------------------
    # 数据基线（接口响应结构）
    # -----------------------------------------------------------
    def save_data(self, case_id, name, data):
        p = self.data_path(case_id, name)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)
        return str(p)

    def load_data(self, case_id, name):
        p = self.data_path(case_id, name)
        if not p.exists():
            return None
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)

    def compare_data(self, case_id, name, current):
        old = self.load_data(case_id, name)
        if old is None:
            if self.auto_create:
                self.save_data(case_id, name, current)
                return {"status": "created", "changes": []}
            return {"status": "missing", "changes": []}
        changes = diff.dict_diff(old, current)
        return {"status": "same" if not changes else "changed",
                "changes": changes}

    # -----------------------------------------------------------
    # 维护
    # -----------------------------------------------------------
    def list_all(self):
        rows = []
        for d in sorted(self.dir.glob("*")):
            if d.is_dir():
                rows.append({"case": d.name,
                             "images": len(list(d.glob("*.png"))),
                             "data": len(list(d.glob("*.json")))})
        return rows

    def prune(self, keep_case_ids):
        keep = {safe_name(c) for c in keep_case_ids}
        removed = 0
        for child in self.dir.iterdir():
            if child.is_dir() and child.name not in keep:
                shutil.rmtree(child, ignore_errors=True)
                removed += 1
        return removed


def schema_of(obj, depth=0):
    """
    提取 JSON 的结构骨架（只保留字段名和类型，丢掉具体值）。

    用于接口结构回归：值可以变，结构不能随便变。
    比如某个字段从 int 变成 string，或者字段消失了，都要告警。
    """
    if depth > 4:
        return "..."
    if isinstance(obj, dict):
        return {k: schema_of(v, depth + 1) for k, v in sorted(obj.items())}
    if isinstance(obj, list):
        return [schema_of(obj[0], depth + 1)] if obj else []
    return type(obj).__name__
