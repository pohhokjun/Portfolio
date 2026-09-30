"""TG 机器人通道：白名单里的人发消息 = 派活（每个聊天一个会话，接着聊），附件存进 工作区/收件。
审批/提问推给主人（白名单第一个），主人回「批 A1」「拒 A1 理由」「答 A1 内容」。跑完把交付的字和文件发回去。
发图片/文件也行：存进 工作区/收件，图片模型直接看。要 TG_BOT_TOKEN、TG_API_ID、TG_API_HASH、TG_USERS。
"""
import re

import 环境
from 核心 import 审批, 监控, 调度
from 核心 import 附件 as 附件库


def 解析指令(文: str):
    """→ (号, 通过, 文本) 或 None"""
    if m := re.match(r"^\s*(批|拒)\s*(A\d+)\s*(.*)$", 文, re.S):
        return m[2], m[1] == "批", m[3].strip()
    if m := re.match(r"^\s*答\s*(A\d+)\s+(.+)$", 文, re.S):
        return m[1], True, m[2].strip()
    return None


async def 开():
    if not 环境.TG["令牌"]:
        return
    from telethon import TelegramClient, events
    bot = TelegramClient(str(环境.记忆 / "tg_bot"), int(环境.TG["api_id"]), 环境.TG["api_hash"])
    await bot.start(bot_token=环境.TG["令牌"])
    主人 = 环境.TG["白名单"][0] if 环境.TG["白名单"] else None

    @bot.on(events.NewMessage(incoming=True))
    async def 收(e):
        if 环境.TG["白名单"] and e.sender_id not in 环境.TG["白名单"]:
            return
        文 = e.raw_text or ""
        if 指令 := 解析指令(文):
            await e.reply("收到" if 审批.回复(*指令) else "这个号不在等了")
            return
        附件 = []
        if e.file:   # 图片/文件：存进 收件，图片模型直接看
            数据 = await e.download_media(file=bytes)
            附件.append(附件库.存(e.file.name or f"tg{e.id}{e.file.ext or ''}", 数据))
        if 文.strip() or 附件:
            编号 = await 调度.提交(文 or "看附件", 会话=f"tg:{e.chat_id}", 来源=f"tg:{e.chat_id}", 附件=附件)
            await e.reply(f"收到，{编号} 在做")

    async def 投递(来源, r):
        聊 = int(来源.split(":", 1)[1])
        if r["出错"]:
            await bot.send_message(聊, f"{r['编号']} 没做成：{r['出错']}")
        for d in r["交付"] or [{"文本": r["回复"] or "（做完了，没有要说的）", "文件": []}]:
            await bot.send_message(聊, d["文本"][:4000], file=d["文件"] or None)

    async def 通知(条):
        if 主人:
            await bot.send_message(主人, f"【{条['号']}】{条['编号']} {'要批准' if 条['类型'] == '批' else '要你回答'}：\n{条['内容']}\n\n"
                                        + (f"回「批 {条['号']}」或「拒 {条['号']} 理由」" if 条["类型"] == "批" else f"回「答 {条['号']} 内容」"))

    async def 告警(文本):
        if 主人:
            await bot.send_message(主人, 文本)

    调度.投递["tg"] = 投递
    审批.通知.append(通知)
    监控.通知.append(告警)
    await bot.run_until_disconnected()
