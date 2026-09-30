# -*- coding: utf-8 -*-
"""
测试结果通知

【来源】从原 17_测试/core/notify.py 迁移，改用 requests。

用途：测试跑完自动把结果推到 Telegram 或企业 Webhook（钉钉/飞书/企业微信）。

★ 为什么这是加分项 ★
    自动化的价值不只是「跑得快」，更是「出问题第一时间有人知道」。
    没有通知的自动化，等于没人看的报告。

    面试话术：
        「我做了通知模块，默认只在有失败时才发，避免通知疲劳。
          支持 Telegram 和通用 Webhook，可以接钉钉飞书。
          消息里带通过率、失败明细和报告链接。」

配置在 config/defaults.yaml 的 notify 段，默认关闭。
"""

import requests

from config.settings import get_config
from common.logger import get_logger

log = get_logger("notify")


class Notifier:
    def __init__(self, cfg=None):
        self.cfg = cfg or get_config()
        self.conf = self.cfg.get("notify", {}) or {}
        self.enabled = bool(self.conf.get("enabled", False))
        self.on = set(self.conf.get("on", ["fail"]))

    def should_send(self, summary):
        """判断是否满足发送条件。"""
        if not self.enabled:
            return False
        if "always" in self.on:
            return True
        if "fail" in self.on and (summary.get("failed", 0) > 0
                                  or summary.get("error", 0) > 0):
            return True
        return False

    def build_text(self, meta, summary):
        total = summary.get("total", 0)
        passed = summary.get("passed", 0)
        rate = round(passed / total * 100, 1) if total else 0

        lines = [
            "【自动化测试报告】",
            "环境: %s   耗时: %ss" % (meta.get("env", ""), meta.get("duration", 0)),
            "用例: %d   通过率: %.1f%%" % (total, rate),
            "通过 %d  失败 %d  异常 %d  跳过 %d" % (
                passed, summary.get("failed", 0),
                summary.get("error", 0), summary.get("skipped", 0)),
        ]

        failures = meta.get("failures") or []
        if failures:
            lines.append("")
            lines.append("失败用例:")
            for name in failures[:10]:
                lines.append("  · %s" % name[:70])
            if len(failures) > 10:
                lines.append("  ... 其余 %d 条见报告" % (len(failures) - 10))

        if meta.get("report"):
            lines.append("")
            lines.append("报告: %s" % meta["report"])
        return "\n".join(lines)

    def send(self, meta, summary, force=False):
        if not force and not self.should_send(summary):
            return {"sent": False, "reason": "未触发通知条件"}

        text = self.build_text(meta, summary)
        results = {}

        tg = self.conf.get("telegram", {}) or {}
        if tg.get("enabled"):
            results["telegram"] = self._telegram(text, tg)

        wh = self.conf.get("webhook", {}) or {}
        if wh.get("url"):
            results["webhook"] = self._webhook(text, wh, meta, summary)

        if not results:
            log.info("未配置通知渠道，内容如下：\n%s", text)
            return {"sent": False, "reason": "无可用渠道", "text": text}
        return {"sent": True, "channels": results}

    # -----------------------------------------------------------
    def _telegram(self, text, tg):
        token, chat_id = tg.get("token"), tg.get("chat_id")
        if not token or not chat_id:
            return "缺少 token/chat_id"
        try:
            url = "https://api.telegram.org/bot%s/sendMessage" % token
            r = requests.post(url, json={"chat_id": chat_id, "text": text,
                                         "disable_web_page_preview": True},
                              timeout=15)
            return "ok" if r.status_code == 200 else "http %s" % r.status_code
        except Exception as exc:
            log.warning("Telegram 通知失败: %s", exc)
            return str(exc)

    def _webhook(self, text, wh, meta, summary):
        """通用 Webhook，兼容钉钉/飞书/企业微信的文本消息格式。"""
        try:
            payload = dict(wh.get("extra", {}) or {})
            payload.update({
                "text": text,
                "msgtype": "text",
                "content": {"text": text},       # 飞书格式
                "meta": meta,
                "summary": summary,
            })
            r = requests.post(wh["url"], json=payload,
                              headers=wh.get("headers") or {}, timeout=15)
            return "ok" if 200 <= r.status_code < 300 else "http %s" % r.status_code
        except Exception as exc:
            log.warning("Webhook 通知失败: %s", exc)
            return str(exc)
