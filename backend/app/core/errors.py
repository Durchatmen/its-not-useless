"""统一业务错误码与业务异常（《接口文档》2.5 通用错误码表）。

码值与前端 frontend/src/utils/errorCode.js 一一对应，新增码值需两处同步。
接口层只需让 BizError 冒泡，由全局异常处理器转成统一响应信封。
"""

from __future__ import annotations

from enum import IntEnum


class ErrorCode(IntEnum):
    SUCCESS = 0
    ACCOUNT_OR_PASSWORD = 1001  # 账号或密码错误
    ACCOUNT_EXISTS = 1002  # 账号已存在
    SMS_CODE_INVALID = 1003  # 短信验证码错误或已过期
    REAL_NAME_FAILED = 1004  # 实名认证失败（姓名与身份证号不一致）
    NO_SCHEDULE = 2001  # 号源不足或已被占用
    APPOINTMENT_INVALID = 2002  # 挂号单不存在或当前状态不允许该操作
    PATIENT_INVALID = 2003  # 就诊人信息校验失败
    BILL_INVALID = 3001  # 账单不存在或已缴费
    PAY_CHANNEL_FAILED = 3002  # 支付渠道（微信/支付宝）下单失败
    PAY_TIMEOUT = 3003  # 支付超时或用户取消支付
    PARAM_INVALID = 4001  # 参数校验失败
    UNAUTHORIZED = 4002  # 未登录或 Token 无效/过期
    FORBIDDEN = 4003  # 无权访问该资源
    HIS_FAILED = 5001  # 医院 HIS 系统调用失败
    LLM_FAILED = 5002  # 大模型服务调用失败或超时
    RAG_FAILED = 5003  # 知识库检索失败
    AMAP_FAILED = 5004  # 高德地图服务调用失败
    INTERNAL = 9999  # 系统内部错误


# 直接写进响应 message 的默认文案；业务侧可传入更具体的提示覆盖
ERROR_MESSAGES: dict[int, str] = {
    ErrorCode.ACCOUNT_OR_PASSWORD: "账号或密码错误",
    ErrorCode.ACCOUNT_EXISTS: "账号已存在",
    ErrorCode.SMS_CODE_INVALID: "短信验证码错误或已过期",
    ErrorCode.REAL_NAME_FAILED: "实名认证失败，请核对姓名与身份证号",
    ErrorCode.NO_SCHEDULE: "号源不足或已被占用，请更换时段",
    ErrorCode.APPOINTMENT_INVALID: "挂号单不存在或当前状态不允许该操作",
    ErrorCode.PATIENT_INVALID: "就诊人信息校验失败",
    ErrorCode.BILL_INVALID: "账单不存在或已缴费",
    ErrorCode.PAY_CHANNEL_FAILED: "支付下单失败，请稍后重试",
    ErrorCode.PAY_TIMEOUT: "支付超时或已取消",
    ErrorCode.PARAM_INVALID: "参数校验失败",
    ErrorCode.UNAUTHORIZED: "未登录或登录已过期，请重新登录",
    ErrorCode.FORBIDDEN: "无权访问该资源",
    ErrorCode.HIS_FAILED: "医院系统繁忙，请稍后重试",
    ErrorCode.LLM_FAILED: "AI 服务繁忙，请稍后重试",
    ErrorCode.RAG_FAILED: "知识库检索失败，请稍后重试",
    ErrorCode.AMAP_FAILED: "地图服务不可用",
    ErrorCode.INTERNAL: "系统内部错误",
}


def message_of(code: int, override: str | None = None) -> str:
    """取错误码对应的提示文案。"""
    if override:
        return override
    return ERROR_MESSAGES.get(int(code), "请求失败，请稍后重试")


class BizError(Exception):
    """业务异常：携带接口错误码，由全局异常处理器转成 {code, message, data:null}。"""

    def __init__(self, code: ErrorCode | int, message: str | None = None) -> None:
        self.code = int(code)
        self.message = message_of(self.code, message)
        super().__init__(self.message)

    def __str__(self) -> str:  # pragma: no cover - 日志可读性
        return f"[{self.code}] {self.message}"
