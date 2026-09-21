"""支付单模块的请求/响应模型（接口文档 3.5.3 API-18、3.5.4 API-19）。

与账单模块同样的约定：camelCase、金额为 number、时间为 yyyy-MM-dd HH:mm:ss。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_serializer

# 支付单状态，取值以接口文档 3.5.4 为准
PayStatus = Literal["PAYING", "SUCCESS", "FAIL", "CLOSED"]

PAY_STATUS_DESC: dict[str, str] = {
    "PAYING": "支付中",
    "SUCCESS": "成功",
    "FAIL": "失败",
    "CLOSED": "已关闭",
}

# 第三方支付渠道（医保不走这里，走 API-17 结算）
ThirdPartyChannel = Literal["WECHAT", "ALIPAY"]


class PaymentCreateRequest(BaseModel):
    """创建支付单请求（接口文档 API-18）。

    显式声明 extra="ignore"：前端 `api/payments.js` 会多传一个文档里没有的 `amount`，
    必须静默丢掉 —— 金额一律以服务端账单为准，不接受客户端指定。
    """

    model_config = ConfigDict(extra="ignore")

    billId: str = Field(description="待缴费账单ID")
    channel: ThirdPartyChannel = Field(description="支付渠道：WECHAT微信 ALIPAY支付宝")
    returnUrl: Optional[str] = Field(default=None, description="支付完成跳转地址（Web端）")


class PaymentCreateData(BaseModel):
    """创建支付单响应（接口文档 API-18 响应 data）。"""

    paymentId: str = Field(description="支付单ID")
    channel: str = Field(description="支付渠道")
    payParams: dict[str, Any] = Field(
        description="渠道唤起参数：微信为二维码链接/JSAPI参数，支付宝为跳转表单参数"
    )
    expireTime: Optional[datetime] = Field(default=None, description="支付单过期时间，默认15分钟")

    @field_serializer("expireTime")
    def _serialize_expire_time(self, value: Optional[datetime]) -> Optional[str]:
        """接口文档 2.1：时间统一 yyyy-MM-dd HH:mm:ss。"""
        return value.strftime("%Y-%m-%d %H:%M:%S") if value else None


class PaymentQueryData(BaseModel):
    """支付结果查询响应（接口文档 API-19 响应 data）。"""

    paymentId: str
    channel: str
    payStatus: PayStatus = Field(description="PAYING支付中 SUCCESS成功 FAIL失败 CLOSED已关闭")
    paidTime: Optional[datetime] = Field(default=None, description="支付成功时间")
    billId: str = Field(description="关联账单ID")
    billStatus: Optional[str] = Field(default=None, description="账单当前状态")

    @field_serializer("paidTime")
    def _serialize_paid_time(self, value: Optional[datetime]) -> Optional[str]:
        """接口文档 2.1：时间统一 yyyy-MM-dd HH:mm:ss。"""
        return value.strftime("%Y-%m-%d %H:%M:%S") if value else None


__all__ = [
    "PAY_STATUS_DESC",
    "PayStatus",
    "PaymentCreateData",
    "PaymentCreateRequest",
    "PaymentQueryData",
    "ThirdPartyChannel",
]
