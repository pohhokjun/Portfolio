"""打码 + 提示词注入检测。

打码：手机号（中国/马来）、身份证、银行卡、邮箱。用在轨迹日志、发给第三方模型前、（可选）交付文字，按业务配置开关。
注入：外部来的文字（需求、工具结果、网页、文件）里出现「忽略之前的指令」这类话，不拦，但记下、告警、
      并在工具结果后面补一句提醒给模型——拦了会误伤正常内容，提醒 + 规则里写明「数据不是指令」更稳。
"""
import re

_码 = [
    (re.compile(r"(?<![\w@])[\w.+-]+@[\w-]+\.[\w.-]+"), lambda m: m[0][:2] + "***@***"),
    (re.compile(r"(?<!\d)\d{6}(?:19|20)\d{2}(?:0[1-9]|1[0-2])\d{2}\d{3}[\dXx](?!\d)"), lambda m: m[0][:4] + "**********" + m[0][-4:]),
    (re.compile(r"(?<!\d)(?:\d[ -]?){15,18}\d(?!\d)"), lambda m: re.sub(r"\d(?=(?:[ -]?\d){4})", "*", m[0])),
    (re.compile(r"(?<!\d)(?:\+?86[ -]?)?1[3-9]\d{9}(?!\d)"), lambda m: m[0][:-8] + "****" + m[0][-4:]),
    (re.compile(r"(?<!\d)(?:\+?60[ -]?|0)1\d[ -]?\d{3,4}[ -]?\d{4}(?!\d)"), lambda m: m[0][:-4].rstrip()[:4] + "****" + m[0][-4:]),
]

_注入 = re.compile(
    r"(忽略|无视|不要理会|别管)[^，。\n]{0,4}(之前|以上|上面|前面|所有|全部)[^，。\n]{0,4}(指令|规则|设定|提示词?|要求)|你现在(是|扮演)|"
    r"(输出|泄露|打印|告诉我)你的?(系统提示|提示词|设定|system prompt)|"
    r"ignore (all |any )?(previous|prior|above) (instructions|rules)|disregard (the )?(previous|above)|"
    r"you are now|system prompt|<\s*/?\s*(system|instructions?)\s*>", re.I)


def 打码(文):
    if not isinstance(文, str):
        return 文
    for 式, 换 in _码:
        文 = 式.sub(换, 文)
    return 文


def 疑似注入(文) -> str:
    """→ 命中的那段（空 = 没有）"""
    m = _注入.search(文 if isinstance(文, str) else str(文))
    return m[0] if m else ""
