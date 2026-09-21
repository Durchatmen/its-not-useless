"""短信验证码：发送与校验（《接口文档》3.1.3 API-03）。

规则：同号同场景 60 秒内不可重复发送，验证码 5 分钟内有效，校验通过即置为已使用。
落库表 t_sms_code；短信网关未配置（sms_gateway_url 为空）时走开发模式——
验证码不真正下发，只写日志，便于本地联调（生产必须配置网关地址）。
"""

from __future__ import annotations

import logging
import secrets
from datetime import timedelta

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import BizError, ErrorCode
from app.models import SmsCode
from app.schemas.common import SmsScene
from app.utils.id_gen import next_id
from app.utils.time_utils import now

logger = logging.getLogger(__name__)


def issue_code(
    db: Session, phone: str, scene: SmsScene | str = SmsScene.REGISTER
) -> SmsCode:
    """生成、下发并落库一条验证码，返回记录（开发模式可直接读 .code 联调）。"""
    scene_value = _value_of(scene)
    _assert_resend_interval(db, phone, scene_value)

    code = f"{secrets.randbelow(1_000_000):06d}"
    sent_at = now()
    row = SmsCode(
        sms_id=next_id(db, SmsCode.sms_id, "SMS"),
        phone=phone,
        code=code,
        scene=scene_value,
        # 显式用应用时钟写入发送时间：created_at 的 server_default 取数据库时钟，
        # 与 _assert_resend_interval / verify_code 里的 now() 不同源（相差时区即失效）
        created_at=sent_at,
        expired_at=sent_at + timedelta(minutes=settings.sms_code_ttl_minutes),
        used_status=0,
    )
    db.add(row)
    db.flush()
    _dispatch(phone, code, scene_value)
    return row


def verify_code(
    db: Session, phone: str, code: str, scene: SmsScene | str = SmsScene.REGISTER
) -> None:
    """校验验证码；未发送、已使用、已过期、不匹配统一抛 1003。"""
    scene_value = _value_of(scene)
    row = db.execute(
        select(SmsCode)
        .where(
            SmsCode.phone == phone,
            SmsCode.scene == scene_value,
            SmsCode.used_status == 0,
        )
        .order_by(SmsCode.created_at.desc(), SmsCode.sms_id.desc())
        .limit(1)
    ).scalar_one_or_none()

    if row is None or row.code != code or row.expired_at < now():
        raise BizError(ErrorCode.SMS_CODE_INVALID)

    row.used_status = 1
    db.flush()


# --------------------------------------------------------------------------- #
# 内部实现
# --------------------------------------------------------------------------- #


def _value_of(scene: SmsScene | str) -> str:
    return getattr(scene, "value", str(scene))


def _assert_resend_interval(db: Session, phone: str, scene: str) -> None:
    """60 秒限发；接口文档未定义专用错误码，按参数校验失败返回并给出剩余秒数。"""
    latest = db.execute(
        select(SmsCode)
        .where(SmsCode.phone == phone, SmsCode.scene == scene)
        .order_by(SmsCode.created_at.desc(), SmsCode.sms_id.desc())
        .limit(1)
    ).scalar_one_or_none()

    if latest is None or latest.created_at is None:
        return
    elapsed = now() - latest.created_at
    # elapsed < 0 只会出现在演示数据里（seed 会把验证码时间铺到当天稍后），不拦
    if timedelta(0) <= elapsed < timedelta(seconds=settings.sms_resend_seconds):
        remain = settings.sms_resend_seconds - int(elapsed.total_seconds())
        raise BizError(ErrorCode.PARAM_INVALID, f"验证码发送过于频繁，请{max(remain, 1)}秒后重试")


def _dispatch(phone: str, code: str, scene: str) -> None:
    """调用短信网关下发验证码。"""
    if not settings.sms_gateway_url:
        logger.info(
            "短信网关未配置（sms_gateway_url 为空），验证码仅记日志：phone=%s scene=%s code=%s",
            phone,
            scene,
            code,
        )
        return

    payload = {
        "phone": phone,
        "code": code,
        "scene": scene,
        "signName": settings.sms_sign_name,
        "expireMinutes": settings.sms_code_ttl_minutes,
    }
    try:
        with httpx.Client(timeout=settings.sms_timeout) as client:
            response = client.post(
                settings.sms_gateway_url,
                json=payload,
                headers={"Authorization": f"Bearer {settings.sms_api_key}"},
            )
            response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.error("短信网关调用失败：phone=%s scene=%s err=%s", phone, scene, exc)
        raise BizError(ErrorCode.INTERNAL, "验证码发送失败，请稍后重试") from exc
