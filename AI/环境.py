"""全局配置。换大脑、换业务都在这（或用环境变量），别处一个字不用动。"""
import os
from pathlib import Path

根 = Path(__file__).resolve().parent

# ── 业务 ───────────────────────────────────────────────
# 一个业务 = 业务/<名字>/ 一个文件夹：人设.md、工具.py、知识/、团队/、定时.json、评测.jsonl。BIZ=名字 切换。
业务名 = os.environ.get("BIZ", "示例")
业务 = 根 / "业务" / 业务名
_家 = Path(os.environ.get("AI_HOME", 根))   # 测试时指到临时目录，不碰正式数据
工作区 = _家 / "工作区" / 业务名          # agent 干活、出产物的地方；闸门只许写这里
记忆 = _家 / "记忆" / 业务名              # 轨迹、台账、会话、待办、知识索引
临时 = 记忆 / "临时"                     # agent 的一次性脚本放这，用完即删
for _d in (工作区, 记忆, 临时):
    _d.mkdir(parents=True, exist_ok=True)

# ── 大脑 ───────────────────────────────────────────────
# 本机 = 本机 Claude Code 的登录（订阅额度，不用 Key）——默认
# api  = Anthropic 官方 API，要 ANTHROPIC_API_KEY
# 兼容 = OpenAI 兼容接口（DeepSeek / 通义 / OpenAI / Ollama…），经 核心/网关.py 翻译，要 COMPAT_*
# 框架都是 Claude Code 那一套（循环、工具、上下文压缩、session），换大脑只是换请求发去哪。
大脑 = os.environ.get("BRAIN", "本机")
备用大脑 = [x for x in os.environ.get("BRAIN_FALLBACK", "").split(",") if x]   # 整单挂了按顺序换，如 "api,兼容"
CLI = Path.home() / ".local/bin/claude.exe"   # 本机自动更新的 Claude Code；SDK 自带的太旧跑不了新模型
模型 = os.environ.get("MODEL", "opus")         # 本机 / api 用；别名自动跟最新
兼容 = {
    "地址": os.environ.get("COMPAT_BASE_URL", "https://api.deepseek.com/v1"),
    "密钥": os.environ.get("COMPAT_API_KEY", ""),
    "模型": os.environ.get("COMPAT_MODEL", "deepseek-chat"),
    "端口": 8792,
}

# ── 一单的封顶 ─────────────────────────────────────────
档位 = {"effort": os.environ.get("EFFORT", "medium"), "max_turns": int(os.environ.get("MAX_TURNS", 60))}
单笔上限 = float(os.environ.get("MAX_USD_PER_TASK", 3))     # 美元，SDK 超了自己停
单笔超时 = int(os.environ.get("TASK_TIMEOUT", 1800))       # 秒，一单跑太久就停（含等人批准的时间）
每日上限 = float(os.environ.get("MAX_USD_PER_DAY", 30))     # 今天花到这就不接新单
重试 = 1                                                   # 同一大脑崩了再试几次（不含换备用）
并发 = int(os.environ.get("CONCURRENCY", 3))                # 服务模式同时跑几单；同一会话仍一单接一单

# ── 工具与权限 ─────────────────────────────────────────
# mcp__biz = 业务工具 + 框架自带工具（查资料、记住、定时、问人、交付）。Task/Agent = 派给 团队/ 里的子 agent。
工具 = ["Read", "Write", "Edit", "Bash", "PowerShell", "Glob", "Grep", "Task", "Agent", "mcp__biz"]
# 无人值守，不停下来问；真正的护栏是 核心/闸门.py 的钩子，这个模式下照样拦得住。
权限模式 = "bypassPermissions"
子环境 = {"PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1", "ENABLE_TOOL_SEARCH": "false"}
审批超时 = 600       # 秒；等人批准/回答，超时算拒绝

# ── 通道 ───────────────────────────────────────────────
HTTP端口 = int(os.environ.get("PORT", 8780))
HTTP令牌 = os.environ.get("API_TOKEN", "")          # 设了就要求请求头 X-Token
限流 = int(os.environ.get("RATE_LIMIT", 30))         # 每个令牌/IP 每分钟最多提交几次
TG = {
    "令牌": os.environ.get("TG_BOT_TOKEN", ""),
    "api_id": os.environ.get("TG_API_ID", ""),
    "api_hash": os.environ.get("TG_API_HASH", ""),
    "白名单": [int(x) for x in os.environ.get("TG_USERS", "").split(",") if x.strip()],   # 只接这些用户，第一个是主人（收审批）
}
