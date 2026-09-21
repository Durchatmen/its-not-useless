"""账号与身份信息的格式校验（注册、实名认证、就诊人管理共用）。

校验规则与前端 frontend/src/views/auth/Register.vue 保持一致：
手机号 11 位、密码至少 6 位、身份证号 18 位。
"""

from __future__ import annotations

import re

PHONE_PATTERN = re.compile(r"^1\d{10}$")
IDCARD_PATTERN = re.compile(r"^\d{17}[\dXx]$")
SMS_CODE_PATTERN = re.compile(r"^\d{6}$")

PASSWORD_MIN_LENGTH = 6
# bcrypt 只使用前 72 字节，超长口令直接拒绝，避免“后半段不参与校验”的隐式截断
PASSWORD_MAX_LENGTH = 64

_IDCARD_WEIGHTS = (7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2)
_IDCARD_CHECKSUM = "10X98765432"


def is_valid_phone(phone: str | None) -> bool:
    """11 位手机号（1 开头）。"""
    return bool(phone) and bool(PHONE_PATTERN.match(phone))


def is_valid_password(password: str | None) -> bool:
    return bool(password) and PASSWORD_MIN_LENGTH <= len(password) <= PASSWORD_MAX_LENGTH


def is_valid_idcard(idcard: str | None, *, checksum: bool = False) -> bool:
    """18 位身份证号。

    checksum=False 时只校验格式（接口文档 3.1.2 对 idcard 的要求即“18位身份证号”，
    演示环境手输的号码时常校验位不合法，故默认不拦）；
    需要严格核验（对接公安/医保接口前的本地预检）时传 checksum=True。
    """
    if not idcard or not IDCARD_PATTERN.match(idcard):
        return False
    if not checksum:
        return True
    total = sum(int(idcard[i]) * _IDCARD_WEIGHTS[i] for i in range(17))
    return _IDCARD_CHECKSUM[total % 11] == idcard[17].upper()
