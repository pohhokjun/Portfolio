# Agent 框架

在 Claude Agent SDK（Claude Code 那套循环、工具、上下文压缩、子 agent）上搭的业务模板。
新业务只写一个文件夹，框架负责大脑、护栏、审批、知识库、记忆、流程、定时、多通道、MCP、安全、监控、评测。

## 用法

| 命令 | 作用 |
|---|---|
| `python Work.py "需求" [@文件]` | 跑一单，审批/提问在终端答；@ 开头是附件 |
| `python Work.py` | 交互模式，输入「接着」续上一单 |
| `python Work.py 服务` | 网页 API + 看板 http://127.0.0.1:8780 + TG + 定时 |
| `python Work.py 流程 [名 k=v]` | 列出 / 跑固定流程，如 `流程 月报 月份=9` |
| `python Work.py 评测 [名字]` | 跑业务评测集 |
| `python Work.py 评测 对比 v1,v2 [名字]` | 人设 A/B 对比 |
| `python Work.py mcp` | 把业务开放成 MCP 服务（stdio） |
| `python Work.py 检查` | 看配置 |
| `python Work.py 用户 加 张三 派活,查看 5` | 发一个 API 令牌（权限、每日上限 $5）；`用户 删 张三`、`用户` 列出 |
| `python -m pytest -q tests` | 58 个离线测试（不调模型） |

## 能力

| 能力 | 在哪 |
|---|---|
| 大脑：本机登录 / Anthropic API / OpenAI 兼容，重试 + 备用大脑 | 核心/大脑.py、网关.py |
| 工具注册、参数校验退回 | 核心/工具.py |
| 结构化输出（JSON schema，字段名用英文） | 跑一单(输出格式=)、API `schema` |
| RAG 知识库（关键词 + 语义，带出处，自动重建） | 核心/知识库.py |
| 多 Agent（子 agent） | 业务/<名>/团队/ |
| 固定工作流（agent / 函数 / 工具 / 审批 步骤，条件、重试、并行组） | 核心/流程.py、业务/<名>/流程/ |
| MCP：接外部服务 + 开放给别的客户端 | 业务/<名>/mcp.json、核心/mcp出口.py |
| 浏览器（读网页；操作网页要批准；域名白名单） | 核心/浏览器.py |
| 人工审批 / 问人（终端、网页、TG），超时算拒 | 核心/审批.py |
| 护栏：危险命令、只写工作区、密钥、收尾检查 | 核心/闸门.py |
| 安全：打码（日志 / 外发第三方 / 交付）、提示词注入检测 + 提醒 + 告警 | 核心/安全.py |
| 长期记忆（remember，超长自动压缩） | 核心/记忆.py |
| 定时（一次性 + 每天固定，可触发流程） | 核心/定时.py |
| 语义缓存（纯问答，数字不同不命中） | 核心/缓存.py |
| 并行：多单同时跑（不同会话并行，同一会话排队）；流程不占名额；评测串行 | 调度.py |
| 稳定性：单笔超时、每单/每天花费上限、API 限流、停机续做 | 环境.py、调度.py、网页.py |
| 监控：省下工时、一次做成率、人工接管率、审批通过率、缓存命中率；告警（出错、连败、花费 80%、注入） | 核心/监控.py |
| 评测：规则 + 大模型评审，隔离记忆；人设多版本 A/B | 核心/评测.py |
| 通道：命令行、HTTP API（含 SSE 实时推送、同步等结果）、看板、TG | 通道/ |
| 图片多模态：各通道都能带附件，图片直接给模型看（兼容大脑也翻译成 image_url）；过程中 Read 看图、deliver 交付图片 | 核心/附件.py |
| 多用户：每人一个令牌，权限（派活/流程/批准/查看/管理）、个人每日上限、会话按人隔开、谁批的留痕 | 核心/用户.py |

## 新建一个业务

复制 `业务/示例/` 改名，`set BIZ=新名字`。

| 文件 | 写什么 |
|---|---|
| `人设.md` / `人设.v2.md` | 角色、数据、口径、说话方式（`{业务}` `{工作区}` 占位）；多版本做 A/B |
| `工具.py` | `@工具("英文名", "中文描述", {"参数": str}, 高风险=False)`，`raise 退回("原因")`；普通函数给流程用；可选 `需批准命令`、`收尾检查(单)` |
| `配置.json` | 人工分钟、浏览器域名、外发打码、交付打码、日志打码、缓存小时、连续失败告警 |
| `知识/` | md/txt/csv/json/xlsx/docx |
| `团队/*.md` | 子 agent：文件头 name / description / tools / model |
| `流程/*.json` | 固定步骤，见 核心/流程.py 头注释和 示例/流程/月报.json |
| `mcp.json` | 外部 MCP 服务（`{python}` `{业务}` 占位） |
| `定时.json` | `[{"时间": "09:00", "需求": "出日报"}, {"时间": "10:00", "流程": "月报", "输入": {"月份": 9}}]` |
| `评测.jsonl` | 需求、包含、不含、文件、工具、最多轮、批准、回答、评审 |

## 环境变量

| 变量 | 作用 |
|---|---|
| `BRAIN` | `本机`（默认）/ `api`（要 `ANTHROPIC_API_KEY`）/ `兼容`（要 `COMPAT_BASE_URL` `COMPAT_API_KEY` `COMPAT_MODEL`） |
| `BRAIN_FALLBACK` | 备用大脑顺序，如 `api,兼容` |
| `BIZ` `PERSONA` `MODEL` `EFFORT` | 业务、人设版本、模型、思考档位 |
| `MAX_TURNS` `MAX_USD_PER_TASK` `MAX_USD_PER_DAY` `TASK_TIMEOUT` | 封顶 |
| `CONCURRENCY` | 服务模式同时跑几单，默认 3 |
| `PORT` `API_TOKEN` `RATE_LIMIT` | HTTP 端口、管理员令牌、每分钟提交上限（没用户也没 API_TOKEN = 本机单人模式，不查令牌） |
| `TG_BOT_TOKEN` `TG_API_ID` `TG_API_HASH` `TG_USERS` | TG（第一个用户是主人，收审批和告警） |
| `ALERT_WEBHOOK` | 告警 webhook（钉钉/飞书/企业微信群机器人） |
| `EMBED_BASE_URL` `EMBED_API_KEY` `EMBED_MODEL` | 知识库改用接口向量 |

## HTTP API

请求头带 `X-Token: 令牌`（SSE 用 `?token=`）。

| 接口 | 说明 |
|---|---|
| `POST /api/task[?wait=秒]` `{需求/task, 会话/session, 输出格式/schema, 缓存/cache, 附件/files: [{名/name, 数据/data: base64}]}` | 提交；带 wait 就等结果 |
| `GET /api/task/{编号}` / `.../stream` | 结果和轨迹 / SSE 实时推送 |
| `GET /api/flows`、`POST /api/flow/{名}` `{输入/inputs}` | 流程 |
| `POST /api/approve/{号}` `{通过/ok, 文本/text}` | 批准 / 拒绝 / 回答 |
| `GET /api/status`、`GET /api/metrics`、`POST /api/kb/rebuild` | 状态、指标+告警、重建知识库 |


