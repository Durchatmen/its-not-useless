"""账单模块的请求/响应模型（接口文档 3.5.1 API-16、3.5.2 API-17）。

字段名与接口文档一致（camelCase、主键 string），前端 `api/request.js` 解完统一信封后
直接拿 `data` 用，中间没有任何 snake→camel 转换层，所以这里的字段名就是前端读到的名字。

金额一律声明为 `float`：库里是 Numeric(10,2)（Decimal），而 Pydantic 会把 Decimal
序列化成字符串，前端也没有 Number() 兜底 —— 接口文档写的是 number，必须是 number。
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_serializer

# 账单类型 / 账单状态 / 支付渠道，取值以接口文档 2.6 枚举表为准
BillType = Literal["REGISTRATION", "TREATMENT"]
BillStatus = Literal["UNPAID", "PAID", "REFUNDED"]
PayChannel = Literal["INSURANCE", "WECHAT", "ALIPAY"]

BILL_TYPE_DESC: dict[str, str] = {
    "REGISTRATION": "挂号缴费",
    "TREATMENT": "就诊缴费",
}

BILL_STATUS_DESC: dict[str, str] = {
    "UNPAID": "待缴费",
    "PAID": "已缴费",
    "REFUNDED": "已退费",
}

PAY_CHANNEL_DESC: dict[str, str] = {
    "INSURANCE": "医保支付",
    "WECHAT": "微信支付",
    "ALIPAY": "支付宝",
}

# 接口文档 3.5.1：billStatus 缺省只看待缴费
DEFAULT_BILL_STATUS = "UNPAID"


class BillListItem(BaseModel):
    """账单列表项（接口文档 API-16 响应 data.list 内元素）。"""

    billId: str
    billType: BillType
    billTitle: str = Field(description="账单名称，如「门诊挂号费」「CT检查费」")
    amount: float = Field(description="总金额（元）")
    insuranceCover: float = Field(description="医保预估报销金额（元）")
    selfPay: float = Field(description="预估自付金额（元）")
    billStatus: BillStatus
    relatedId: Optional[str] = Field(
        default=None, description="关联业务ID（挂号单/检查单/处方单）"
    )
    createTime: Optional[datetime] = Field(default=None, description="开单时间")

    @field_serializer("createTime")
    def _serialize_create_time(self, value: Optional[datetime]) -> Optional[str]:
        """接口文档 2.1：时间统一 yyyy-MM-dd HH:mm:ss，避免默认的 ISO 8601（带 T）。"""
        return value.strftime("%Y-%m-%d %H:%M:%S") if value else None


class BillListData(BaseModel):
    """分页信封（接口文档 2.1 分页约定）。"""

    total: int
    pageNum: int
    pageSize: int
    list: list[BillListItem]


class BillSettleRequest(BaseModel):
    """账单缴费请求（接口文档 API-17）。

    paymentId 为条件必填：走微信/支付宝时必须先经 API-18 创建支付单，
    条件校验放在 service 里做，这样报错信息能说清缺什么。
    """

    payChannel: PayChannel = Field(description="支付渠道：INSURANCE医保 WECHAT微信 ALIPAY支付宝")
    paymentId: Optional[str] = Field(
        default=None, description="第三方支付单ID，走微信/支付宝时必填（先经 API-18 创建）"
    )


class BillSettleData(BaseModel):
    """账单缴费响应（接口文档 API-17 响应 data）。"""

    billId: str
    billStatus: BillStatus = Field(description="缴费后状态，PAID")
    paidAmount: float = Field(description="实付金额（元）")
    insurancePaid: float = Field(description="医保统筹支付金额（元）")
    invoiceNo: Optional[str] = Field(default=None, description="电子票据号")


__all__ = [
    "BILL_STATUS_DESC",
    "BILL_TYPE_DESC",
    "DEFAULT_BILL_STATUS",
    "PAY_CHANNEL_DESC",
    "BillListData",
    "BillListItem",
    "BillSettleData",
    "BillSettleRequest",
    "BillStatus",
    "BillType",
    "PayChannel",
]
