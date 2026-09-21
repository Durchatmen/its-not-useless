"""多模态输入转文字：图片 OCR/理解 + 语音转写。

技术选型原定 PaddleOCR 做图片、本地 ASR 做语音，但 PaddleOCR 在 Python 3.14
装不上（paddlex 锁 PyYAML==6.0.2，无 cp314 轮子），语音也一直没定 ASR。
现统一改走百炼的 Qwen 多模态模型（同一个 OpenAI 兼容端点，只换 model）：
  - 图片  image_to_text  -> qwen-vl（LLM_VL_MODEL）
  - 语音  audio_to_text  -> qwen-omni（LLM_OMNI_MODEL）

两者都只把输入「翻译成一段可用于预诊分诊的文字」产出 recognizedText，
后续仍走纯文本的预诊链路，不在这里做任何病情判断。
"""

from __future__ import annotations

import base64
import binascii
import logging

from app.core.config import settings
from app.services.llm import LLMError, Message, chat

logger = logging.getLogger(__name__)

IMAGE_PROMPT = (
    "请识别这张图片，把其中与就医相关的信息转成文字描述"
    "（如化验单的指标与数值、皮疹或伤口的部位与外观）。只输出描述文字，不要解释。"
)
AUDIO_PROMPT = "请把这段语音转写成文字。只输出转写出的内容，不要解释、不要加引号。"

# qwen-omni 支持的音频格式；amr 不在其中，需先转成 wav/mp3
_SUPPORTED_AUDIO_FORMATS = {"wav", "mp3"}


def _sniff_image_mime(data: bytes) -> str:
    """按魔数猜图片 MIME。前端只传 base64、不带格式，而 data URL 需要正确的 mime。"""
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if data[:2] == b"BM":
        return "image/bmp"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return "image/jpeg"  # 猜不出就按最常见的 jpeg 兜底


def image_to_text(image_data: str) -> str:
    """图片（Base64）-> 文字描述。image_data 是接口文档里的纯 Base64，不含 data: 前缀。"""
    try:
        raw = base64.b64decode(image_data, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise LLMError(f"imageData 不是合法的 Base64: {exc}") from exc

    mime = _sniff_image_mime(raw)
    messages: list[Message] = [
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{image_data}"}},
                {"type": "text", "text": IMAGE_PROMPT},
            ],
        }
    ]
    return chat(messages, model=settings.llm_vl_model, temperature=0).strip()


def audio_to_text(audio_data: str, audio_format: str | None) -> str:
    """语音（Base64）-> 转写文字。audio_format 取 wav / mp3；amr 等需先转码。"""
    if not audio_format:
        raise LLMError("audioFormat 不能为空，语音输入需注明 wav / mp3")
    fmt = audio_format.lower()
    if fmt not in _SUPPORTED_AUDIO_FORMATS:
        raise LLMError(f"语音格式 {fmt} 暂不支持，请转成 wav 或 mp3 后再传")

    # 先验一下是不是合法 Base64，免得发一个注定失败的请求
    try:
        base64.b64decode(audio_data, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise LLMError(f"audioData 不是合法的 Base64: {exc}") from exc

    messages: list[Message] = [
        {
            "role": "user",
            "content": [
                {"type": "input_audio", "input_audio": {"data": audio_data, "format": fmt}},
                {"type": "text", "text": AUDIO_PROMPT},
            ],
        }
    ]
    return chat(messages, model=settings.llm_omni_model, temperature=0).strip()


__all__ = ["audio_to_text", "image_to_text"]
