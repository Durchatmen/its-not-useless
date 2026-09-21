"""t_payment 支付单表（设计文档 3.11）。"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAtMixin


class Payment(Base, CreatedAtMixin):
    """对接支付宝/微信统一下单、回调与结果查询。"""

    __tablename__ = "t_payment"

    payment_id: Mapped[str] = mapped_column(String(32), primary_key=True, comment="支付单编号")
    bill_id: Mapped[str] = mapped_column(
        ForeignKey("t_bill.bill_id"), nullable=False, comment="账单编号"
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("t_user.user_id"), nullable=False, comment="发起支付的账号编号"
    )
    channel: Mapped[str] = mapped_column(String(16), nullable=False, comment="支付渠道：WECHAT微信支付 ALIPAY支付宝")
    channel_trade_no: Mapped[Optional[str]] = mapped_column(String(64), comment="第三方支付流水号（回调回填）")
    pay_status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="PAYING",
        server_default="PAYING",
        comment="状态：PAYING支付中 SUCCESS成功 FAIL失败 CLOSED已关闭",
    )
    amount: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), nullable=False, default=0, server_default="0.00", comment="支付金额（元）"
    )
    pay_params: Mapped[Optional[str]] = mapped_column(
        Text, comment="渠道唤起参数（二维码链接/JSAPI参数，JSON）"
    )
    expire_time: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="支付单过期时间（默认15分钟）")
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="支付成功时间")
    callback_at: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="回调到达时间")
