"""v1 路由总装（接口文档 3 章，接口基础地址 /api/v1）。

每个业务模块自带 `APIRouter(prefix=..., tags=...)`，这里只做汇总与挂载 ——
业务代码一行都不在本文件里，加/减模块只改这里的 imports 与 include_router。

挂载顺序 = Swagger 文档里分组的显示顺序，按接口文档 3.1 ~ 3.11 的章节排，
不按字母序：`/docs` 打开后与需求方的接口清单一一对上，评审时省得来回找。

路由数量与接口文档的对应关系（共 30 条）：
    用户认证    API-01 ~ 03   （+ /auth/login/sms，功能设计文档要求的第二种登录方式）
    AI 预诊分诊 API-08 ~ 09
    就诊人管理  API-04 ~ 07
    挂号模块    API-10 ~ 15   （schedules 与 appointments 同属挂号模块）
    检查模块    API-24 ~ 29   （+ 检查列表）
    支付模块    API-16 ~ 19   （bills 与 payments 同属支付模块）
    病历        API-22 ~ 23
    用药        API-30       （+ 用药提醒 API-31，挂在 medication-reminders 前缀下）
    院外导航    API-20
    医保        API-32

⚠ 未实现：API-21 院内导航（该功能已从需求范围中砍掉，见 navigation_service 的说明）。
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import (
    ai,
    appointments,
    auth,
    bills,
    exams,
    insurance,
    medical_records,
    medication_reminders,
    navigation,
    patients,
    payments,
    prescriptions,
    schedules,
)

# 接口基础地址（接口文档 2.1：https://api.example.com/api/v1）
api_router = APIRouter(prefix="/api/v1")

# 按接口文档章节顺序挂载，Swagger 分组顺序即此顺序
_ROUTERS = (
    auth.router,  # 3.1  用户认证
    ai.router,  # 3.3  多模态预诊
    patients.router,  # 3.2  就诊人管理
    schedules.router,  # 3.4.1 排班与号源
    appointments.router,  # 3.4.2 ~ 3.4.6 挂号
    bills.router,  # 3.5.1 ~ 3.5.2 账单
    payments.router,  # 3.5.3 ~ 3.5.4 支付单
    navigation.router,  # 3.6.1 院外导航
    medical_records.router,  # 3.7  病历
    exams.router,  # 3.8  检查
    prescriptions.router,  # 3.9.1 药单
    medication_reminders.router,  # 3.9.2 用药提醒
    insurance.router,  # 3.10 医保
)

for _router in _ROUTERS:
    api_router.include_router(_router)

__all__ = ["api_router"]
