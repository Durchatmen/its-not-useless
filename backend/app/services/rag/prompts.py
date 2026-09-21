"""预诊 / 分诊 Agent 的提示词与输出契约。

对应接口文档 API-08（`POST /api/v1/ai/multimodal/messages`）：一次调用要产出
`reply`、`triageCard`、`riskWarning`、`sources`、`nextQuestion`、`disclaimer`。

为了让流式（SSE）和非流式共用同一套提示词：
  - 自然语言回复放在最前面，流式时逐段推给前端（delta 事件）；
  - 结构化字段压成一个 `<result>` JSON 块放在最后，收流后一次性解析。
这样正文能边生成边渲染，结构化数据不必等模型把话说完再单独调一次大模型。

本模块只有提示词与常量，不做任何 IO，便于单独测试和迭代。
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.rag.retriever import RetrievedChunk

logger = logging.getLogger(__name__)

# ------------------------------------------------- 固定话术

DISCLAIMER = "以上内容为AI辅助建议，不构成医疗诊断，请以执业医师意见为准。"

# 需求分析 §9 要求急危重症场景触发安全话术并建议拨打120或前往急诊
EMERGENCY_WARNING = (
    "您描述的情况可能属于急危重症，请立即拨打120或前往最近的医院急诊科就诊，不要等待在线回复。"
)

# 结构化结果的包裹标记。用自定义标签而非 ```json 代码块：正文里出现的代码块不会与它混淆，
# 且流式下能靠结束标签明确判定「结构化数据已经到齐」。
RESULT_OPEN = "<result>"
RESULT_CLOSE = "</result>"

# 分诊卡片上「去挂号」按钮的前端动作标识（接口文档 API-08）
BUTTON_GO_REGISTER = "GO_REGISTER"

# ------------------------------------------------- 输出契约

_OUTPUT_CONTRACT = f"""【输出格式】
先用自然语言回复患者，语气平和通俗，面向非医学背景的人，不要用 Markdown 标题或列表符号。
回复结束后另起一行，输出一个 JSON 对象，并用 {RESULT_OPEN} 和 {RESULT_CLOSE} 包裹，字段固定为：

{{
  "triageCard": {{"department": "推荐科室", "location": "科室位置", "doctor": "推荐医生及擅长", "buttonAction": "{BUTTON_GO_REGISTER}"}},
  "riskWarning": "高危症状预警，没有则空字符串",
  "nextQuestion": "还需要了解的关键信息，追问一句；已足够则空字符串",
  "sources": ["本次实际引用的知识库或文档名"]
}}

硬性要求：
- 只输出一个 {RESULT_OPEN} 块，且必须位于正文之后；
- JSON 必须合法、能被 json.loads 直接解析，不要夹注释、不要尾随逗号；
- 知识库里查不到的字段一律不要编造：科室拿不准就把 triageCard 置为 null，
  位置或医生查不到就把对应值置为 null。"""

# ------------------------------------------------- 系统提示词

PRE_DIAGNOSIS_SYSTEM = f"""你是医院智能就医系统的预诊助手，在患者描述症状后给出初步病情分析和就诊科室建议。

工作要求：
1. 只依据【诊疗知识库】中检索到的资料作答，资料未覆盖的内容不要臆测。
2. 你给的是就诊参考而非诊断：不说「您患了XX病」，而说「可能提示XX，建议到XX科就诊」。
3. 不推荐具体药品、剂量或处方；患者问用药，引导其就诊后遵医嘱。
4. 出现胸痛、呼吸困难、意识障碍、大出血、剧烈腹痛、持续高热等急危重症信号时，
   停止常规预诊：riskWarning 原文引用下面这句安全话术（不要改写），
   正文 reply 也只简要提醒尽快就医，不再追问、不再推荐科室：

   {EMERGENCY_WARNING}

5. 判断科室所需信息不足时，通过 nextQuestion 追问最关键的一两个问题
   （如持续时间、伴随症状、既往史），不要一次抛出一串问题。
6. 多轮对话里已经问过的信息不要重复追问。
7. 输入可能是语音转写或图片识别得到的文字，允许存在识别误差，
   遇到明显不通顺处按最可能的医学含义理解，并可在 nextQuestion 里向患者确认。
8. 症状识别失败时的兜底：当患者描述里提取不到任何可辨认的症状（部位、性质、持续时间
   都没有，或内容与就医无关）时，不要硬猜病情，reply 改为引导患者按
   「症状部位 + 持续时间 + 伴随症状」的模板重新描述，并把这个模板原样告诉患者。
9. 预诊断正文 reply 要自然带出两项就诊前提示，用短句表达、不用列表符号：
   「就医前注意事项」（与该症状相关的通用事项，如是否空腹、暂停用药、避免剧烈活动）
   和「需准备资料清单」（身份证/医保卡、既往病历、近期检查报告、正在服用的药物）。

{_OUTPUT_CONTRACT}"""

TRIAGE_SYSTEM = f"""你是医院智能就医系统的分诊助手，负责把预诊结论落实成可执行的挂号推荐。

工作要求：
1. 只依据【科室及医生知识库】中检索到的资料推荐科室、医生与位置，
   绝不编造不存在的科室、医生或诊区位置。
2. triageCard 必须给出 department；location 与 doctor 只有确实检索到时才填，检索不到就置为 null。
3. 推荐医生时要看其擅长领域与患者症状是否匹配，而不是随便挑一个。
4. 患者已明确指定科室时，先尊重其选择，再补充该科室的医生建议。
5. sources 列出本次实际用到的知识库名称。

{_OUTPUT_CONTRACT}"""


# ------------------------------------------------- 解析模型输出

class ResultStreamSplitter:
    """增量切分模型输出：把 `<result>` 之前的正文实时交出，结构化块攒到最后解析。

    流式下每来一个文本块都要判断「能不能往外发」：`<result>` 是逐字符到达的，
    若收到 `<res` 就当作正文推给前端，等 `ult>` 到齐时前面已经发出去、撤不回来。
    所以每次都得扣住尾部 `len(RESULT_OPEN) - 1` 个字符，等下一块来了再决定。
    """

    _HOLD = len(RESULT_OPEN) - 1

    def __init__(self) -> None:
        self._buf = ""
        self._result = ""
        self._saw_open = False
        self._started = False

    def _hold_from(self) -> int:
        """算出「可以安全发出」的上界位置。

        末尾要扣住两样东西：没拼完的 `<result>` 前缀，以及紧挨着它的空白 ——
        空白后头可能跟的就是 `<result>`，先推给前端就再也抹不掉了。
        被扣住的部分等下一个非空白字符到达、窗口右移之后自然会放行。
        """
        start = len(self._buf) - self._HOLD
        while start > 0 and self._buf[start - 1].isspace():
            start -= 1
        return start

    def _emit(self, text: str, *, at_end: bool) -> str:
        """交出正文时抹掉首尾空白，让流式拼出的结果与非流式的逐字一致。

        模型习惯在正文前留空行、在 `<result>` 前空一行；流式没法回头删已推出的字符，
        只能在推之前处理。非流式走同一个类，两边因此天然对齐。
        """
        if not text:
            return ""
        if not self._started:
            text = text.lstrip()
            if not text:
                return ""
            self._started = True
        return text.rstrip() if at_end else text

    def feed(self, chunk: str) -> str:
        """喂入新到的文本块，返回此刻可以安全发出的正文（可能为空串）。"""
        if self._saw_open:
            self._result += chunk
            return ""

        self._buf += chunk
        start = self._buf.find(RESULT_OPEN)
        if start != -1:
            self._saw_open = True
            reply = self._buf[:start]
            self._result = self._buf[start + len(RESULT_OPEN) :]
            self._buf = ""
            return self._emit(reply, at_end=True)

        limit = self._hold_from()
        if limit <= 0:
            return ""
        reply, self._buf = self._buf[:limit], self._buf[limit:]
        return self._emit(reply, at_end=False)

    def finish(self) -> tuple[str, dict]:
        """流结束：返回 (尚未发出的正文尾巴, 解析出的结构化字段)。"""
        if self._saw_open:
            return "", self._parse(self._result)

        tail, self._buf = self._buf, ""
        return self._emit(tail, at_end=True), {}

    @staticmethod
    def _parse(raw: str) -> dict:
        end = raw.find(RESULT_CLOSE)
        if end != -1:
            raw = raw[:end]
        try:
            data = json.loads(raw.strip())
        except json.JSONDecodeError:
            logger.warning("模型输出的 <result> 块不是合法 JSON，已忽略: %s", raw[:120])
            return {}
        return data if isinstance(data, dict) else {}


def split_reply_and_result(text: str) -> tuple[str, dict]:
    """把完整输出拆成 (正文, 结构化字段)，供非流式路径复用同一套解析规则。

    模型没按契约输出 `<result>` 块、或块内 JSON 不合法时，结构化字段返回空 dict，
    正文照常返回 —— 宁可少一张卡片，也不要让整轮对话失败。
    """
    splitter = ResultStreamSplitter()
    reply = splitter.feed(text)
    tail, data = splitter.finish()
    return reply + tail, data


# ------------------------------------------------- 上下文与来源

def format_context(chunks: Sequence["RetrievedChunk"]) -> str:
    """把召回片段拼成带编号的知识库上下文，供提示词注入。

    编号让模型在回复里可以指代具体条目前后印证，来源名则供它写进 sources。
    """
    if not chunks:
        return "（本次没有检索到相关资料。请据实说明暂时无法判断，不要编造内容。）"

    blocks: list[str] = []
    for index, chunk in enumerate(chunks, 1):
        title = chunk.title_path or chunk.source_file or "未命名条目"
        category = chunk.category or "知识库"
        blocks.append(f"[{index}] 来源：{category} / {title}\n{chunk.text.strip()}")
    return "\n\n".join(blocks)


def collect_sources(chunks: Sequence["RetrievedChunk"]) -> list[str]:
    """按出现顺序汇总引用到的知识库名（去重），用作接口响应里的 sources 兜底值。"""
    sources: list[str] = []
    for chunk in chunks:
        name = chunk.category or chunk.source_file
        if name and name not in sources:
            sources.append(name)
    return sources


__all__ = [
    "BUTTON_GO_REGISTER",
    "DISCLAIMER",
    "EMERGENCY_WARNING",
    "PRE_DIAGNOSIS_SYSTEM",
    "RESULT_CLOSE",
    "RESULT_OPEN",
    "ResultStreamSplitter",
    "TRIAGE_SYSTEM",
    "collect_sources",
    "format_context",
    "split_reply_and_result",
]
