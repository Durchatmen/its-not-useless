"""敏感字段确定性加密（《数据库表设计文档》3.3：身份证号加密存储）。

为什么用确定性加密
    身份证号既要密文落库，又要在登录时按“身份证号 = ?”查询命中，因此不能使用
    随机 IV 的 AES-GCM（同一明文每次密文不同，无法等值匹配）。这里用 AES-SIV
    （RFC 5297，cryptography 的 AESSIV）：SIV 模式以密文本身充当认证标签，
    相同明文 + 相同密钥恒定得到相同密文，是“可检索加密”的标准取舍。

代价与边界
    * 确定性密文会泄露“两个用户身份证号是否相同”，不泄露明文本身，符合本项目
      “密文存储 + 等值查询”的需求；若后续要抗频次分析，需改为盲索引方案。
    * 密钥由 settings.secret_key 经 HKDF-SHA256 派生。**更换 secret_key 会导致
      已落库的身份证号无法解密**，上线后需把 secret_key 固定到密钥管理服务。

存储格式
    ``enc:v1:<base64url(密文)>``。带版本前缀是为了把密文与历史明文数据区分开
    （演示数据 app/db/seed.py 里的医生身份证号仍是明文），使等值查询可以同时
    兼容两种形态，也为后续换算法留出升级空间。
"""

from __future__ import annotations

import base64
import binascii
import logging

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESSIV
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.core.config import settings

logger = logging.getLogger(__name__)

# 密文前缀（含版本号），用于区分密文与历史明文
ENCRYPTED_PREFIX = "enc:v1:"
# HKDF 的 salt/info 恒定，保证派生密钥在进程重启后不变（确定性加密的前提）
_KEY_SALT = b"hospital-its-not-useless"
_KEY_INFO = b"idcard-deterministic-encryption"
# AESSIV 需要 64 字节密钥（两半：SIV 与 CTR）
_KEY_SIZE = 64

_aead: AESSIV | None = None


def _cipher() -> AESSIV:
    """惰性构建 AESSIV 实例（进程内复用，派生密钥只算一次）。"""
    global _aead
    if _aead is None:
        _aead = AESSIV(
            HKDF(
                algorithm=SHA256(),
                length=_KEY_SIZE,
                salt=_KEY_SALT,
                info=_KEY_INFO,
            ).derive(settings.secret_key.encode("utf-8"))
        )
    return _aead


def encrypt_text(plain: str) -> str:
    """确定性加密并编码为 ``enc:v1:<base64url>``。

    幂等：入参已是本模块产出的密文时原样返回，避免重复加密。
    """
    if not plain:
        return plain
    if is_encrypted(plain):
        return plain
    sealed = _cipher().encrypt(plain.encode("utf-8"), None)
    return ENCRYPTED_PREFIX + base64.urlsafe_b64encode(sealed).decode("ascii")


def decrypt_text(value: str) -> str:
    """解密 ``enc:v1:`` 密文；非本格式或密钥不匹配时抛 ValueError。"""
    if not is_encrypted(value):
        raise ValueError("不是本模块加密的密文")
    try:
        sealed = base64.urlsafe_b64decode(value[len(ENCRYPTED_PREFIX) :].encode("ascii"))
        return _cipher().decrypt(sealed, None).decode("utf-8")
    except (binascii.Error, InvalidTag, UnicodeDecodeError, ValueError) as exc:
        raise ValueError("密文无法解密（secret_key 是否已更换？）") from exc


def try_decrypt_text(value: str | None) -> str | None:
    """容错解密：明文或解密失败时返回原值/None，供展示类逻辑使用。"""
    if not value or not is_encrypted(value):
        return value
    try:
        return decrypt_text(value)
    except ValueError as exc:
        logger.warning("身份证号解密失败：%s", exc)
        return None


def is_encrypted(value: str | None) -> bool:
    """是否为本模块产出的密文。"""
    return bool(value) and value.startswith(ENCRYPTED_PREFIX)


def equality_candidates(value: str) -> list[str]:
    """等值查询候选值：密文形态在前，明文形态在后。

    注册用户存的是密文，而 app/db/seed.py 生成的演示医生账号是明文身份证号，
    因此登录时两种形态都要匹配，待演示数据重建为密文后可退化为单值查询。
    """
    if not value:
        return []
    encrypted = encrypt_text(value)
    return [encrypted, value] if encrypted != value else [value]
