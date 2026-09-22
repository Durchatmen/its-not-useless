"""登录 / 注册模块数据契约（《接口文档》3.1：API-01 / API-02 / API-03）。

字段名与接口文档一致（camelCase），前端 frontend/src/api/auth.js 直接对接。
"""

from __future__ import annotations

from pydantic import BaseModel, Field, computed_field, field_validator

from app.schemas.common import SmsScene, UserRole
from app.utils.validators import IDCARD_PATTERN, PHONE_PATTERN, is_valid_idcard

SMS_CODE_PATTERN = r"^\d{6}$"
_PASSWORD_FIELD = Field(min_length=6, max_length=64, description="密码，经 HTTPS 传输")


class LoginRequest(BaseModel):
    """API-01 用户登录请求体。"""

    account: str = Field(min_length=1, max_length=64, description="账号，支持手机号或身份证号")
    password: str = Field(min_length=1, max_length=64, description="密码")
    role: UserRole = Field(
        default=UserRole.PATIENT, description="期望登录角色，服务端校验与账号实际角色一致"
    )


class UserInfo(BaseModel):
    """登录后返回的用户信息（接口文档 API-01 响应 userInfo）。"""

    userId: str
    name: str | None = None
    role: UserRole
    phone: str | None = None
    realNameVerified: bool = False


class LoginData(BaseModel):
    """API-01 响应 data。

    除文档规定的 userInfo 外，同时在最外层给出扁平字段：前端 Pinia store
    （frontend/src/stores/user.js 的 setAuth）把 data 直接展开进 profile，
    依赖 profile.name / profile.role / profile.userId。
    """

    accessToken: str = Field(description="JWT 访问令牌")
    expiresIn: int = Field(description="有效期（秒）")
    userInfo: UserInfo

    @computed_field
    @property
    def userId(self) -> str:
        return self.userInfo.userId

    @computed_field
    @property
    def name(self) -> str | None:
        return self.userInfo.name

    @computed_field
    @property
    def role(self) -> UserRole:
        return self.userInfo.role

    @computed_field
    @property
    def phone(self) -> str | None:
        return self.userInfo.phone

    @computed_field
    @property
    def realNameVerified(self) -> bool:
        return self.userInfo.realNameVerified


class RegisterRequest(BaseModel):
    """API-02 用户注册请求体。

    注册不校验短信验证码（产品要求去掉注册环节的验证码校验），只做实名核验。
    验证码能力仍保留给登录场景（SmsLoginRequest）。
    """

    phone: str = Field(pattern=PHONE_PATTERN.pattern, description="11 位手机号，作为登录账号")
    password: str = _PASSWORD_FIELD
    name: str = Field(min_length=1, max_length=32, description="姓名，须与身份证一致")
    idcard: str = Field(pattern=IDCARD_PATTERN.pattern, description="18 位身份证号")

    @field_validator("idcard")
    @classmethod
    def _validate_idcard(cls, value: str) -> str:
        if not is_valid_idcard(value):
            raise ValueError("身份证号格式不正确")
        return value.upper()


class RegisterData(BaseModel):
    """API-02 响应 data。"""

    userId: str = Field(description="新建用户ID")
    realNameVerified: bool = Field(description="实名认证结果")


class SmsCodeRequest(BaseModel):
    """API-03 发送短信验证码请求体。"""

    phone: str = Field(pattern=PHONE_PATTERN.pattern, description="11 位手机号")
    # 接口文档 API-03 把 scene 标为必填，因此不给默认值
    scene: SmsScene = Field(description="用途：LOGIN 登录（注册已不需要验证码）")


class SmsLoginRequest(BaseModel):
    """手机号 + 验证码登录（《功能设计文档》3.1 多方式登录）。

    接口文档当前只收录了账号密码登录，这里先把服务能力备好，
    待接口文档补充 API 编号后再由接口层暴露。
    """

    phone: str = Field(pattern=PHONE_PATTERN.pattern)
    smsCode: str = Field(pattern=SMS_CODE_PATTERN)
    role: UserRole = UserRole.PATIENT
