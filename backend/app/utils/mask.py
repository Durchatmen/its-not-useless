"""敏感字段脱敏。

《接口文档》2.2：检查报告、处方、病历等敏感数据接口执行二次鉴权，
患者仅可访问本人及被授权家属的数据；3.2 查询就诊人列表要求姓名、身份证号、
手机号脱敏展示（如“张*生”）。
"""

from __future__ import annotations


def mask_name(name: str | None) -> str | None:
    """张三 -> 张*；张小三 -> 张*三；复姓等更长姓名保留首尾。"""
    if not name:
        return name
    if len(name) == 1:
        return name
    if len(name) == 2:
        return f"{name[0]}*"
    return f"{name[0]}{'*' * (len(name) - 2)}{name[-1]}"


def mask_phone(phone: str | None) -> str | None:
    """13800008888 -> 138****8888。"""
    if not phone or len(phone) < 7:
        return phone
    return f"{phone[:3]}****{phone[-4:]}"


def mask_idcard(idcard: str | None) -> str | None:
    """330106199001011234 -> 3301**********1234。"""
    if not idcard or len(idcard) < 8:
        return idcard
    return f"{idcard[:4]}{'*' * (len(idcard) - 8)}{idcard[-4:]}"
