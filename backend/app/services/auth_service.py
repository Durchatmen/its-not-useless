"""登录 / 注册业务（《接口文档》3.1 API-01 / API-02 / API-03）。

* 账号：注册时以手机号作为登录账号，登录时账号支持手机号或身份证号；
* 注册只做实名认证（详见 _verify_realname），不校验短信验证码；验证码仅用于登录场景；
* 密码：bcrypt 加盐哈希存储，明文只在请求生命周期内出现，不落库、不写日志；
* 身份证号：AES-SIV 确定性加密存储（app/core/crypto），既能密文落库，又能按
  “身份证号 = ?”等值登录；
* 登录成功签发 JWT，并写一条 LOGIN 操作日志（合规审计留存不少于 6 个月）。

事务边界：本模块写操作自行 commit，调用方（接口层）只需接住 BizError。
"""

from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import crypto
from app.core.errors import BizError, ErrorCode
from app.core.security import create_access_token, hash_password, verify_password
from app.models import OperationLog, SmsCode, User
from app.schemas.auth import (
    LoginData,
    LoginRequest,
    RegisterRequest,
    SmsCodeRequest,
    SmsLoginRequest,
    UserInfo,
)
from app.schemas.common import SmsScene, UserRole
from app.services import sms
from app.utils.id_gen import next_id
from app.utils.time_utils import now
from app.utils.validators import is_valid_idcard

# 注册账号与主键的并发冲突重试次数（见 app/utils/id_gen.next_id 的说明）
_REGISTER_RETRIES = 3


# --------------------------------------------------------------------------- #
# API-03 发送短信验证码
# --------------------------------------------------------------------------- #


def send_code(db: Session, payload: SmsCodeRequest) -> SmsCode:
    """发送短信验证码（登录场景），走 60 秒限发。

    注册已不需要验证码，原 REGISTER 场景的「账号未被占用」前置校验一并移除
    —— 账号是否存在由后续登录/注册各自的校验负责。
    """
    row = sms.issue_code(db, payload.phone, payload.scene)
    db.commit()
    return row


# --------------------------------------------------------------------------- #
# API-02 用户注册
# --------------------------------------------------------------------------- #


def register(db: Session, payload: RegisterRequest) -> User:
    """注册账号（角色固定 PATIENT），返回新建用户。

    只校验账号未被占用 + 实名核验；短信验证码已按产品要求从注册流程移除
    （不再需要 API-03 的 REGISTER 场景验证码）。
    """
    account = payload.phone.strip()
    _assert_account_available(db, account)

    if not _verify_realname(payload.name, payload.idcard):
        raise BizError(ErrorCode.REAL_NAME_FAILED)

    user = _insert_user(db, account, payload)
    _write_log(
        db,
        user_id=user.user_id,
        action="REGISTER",
        detail=f"注册账号 {user.account}（{user.name}），实名认证通过",
    )
    db.commit()
    return user


def _insert_user(db: Session, account: str, payload: RegisterRequest) -> User:
    """插入账号；主键/账号并发冲突时重试，重试仍失败按具体原因返回。"""
    password_hash = hash_password(payload.password)

    for _ in range(_REGISTER_RETRIES):
        user = User(
            user_id=next_id(db, User.user_id, "USR"),
            account=account,
            password=password_hash,
            name=payload.name.strip(),
            # 身份证号确定性加密存储（数据库设计 3.3），仍支持按证件号等值登录
            idcard=crypto.encrypt_text(payload.idcard),
            phone=account,
            role=UserRole.PATIENT.value,
            real_name_verified=1,
            status=1,
        )
        db.add(user)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            _assert_account_available(db, account)
            continue
        return user

    raise BizError(ErrorCode.INTERNAL, "注册失败，请稍后重试")


def _verify_realname(name: str, idcard: str) -> bool:
    """实名核验：姓名须与身份证一致（《接口文档》2.7 公安/医保实名认证接口依赖）。

    演示环境按“姓名非空 + 18 位身份证号且校验位合法”做本地预检，
    因此伪造的身份证号会稳定命中 1004，便于演示实名认证失败分支；
    生产环境在此处替换为政务平台实名认证调用，失败同样返回 False。
    """
    if not name or not name.strip():
        return False
    return is_valid_idcard(idcard, checksum=True)


# --------------------------------------------------------------------------- #
# API-01 用户登录
# --------------------------------------------------------------------------- #


def login(db: Session, payload: LoginRequest, *, ip: str | None = None) -> tuple[User, str, int]:
    """账号（手机号/身份证号）+ 密码登录，返回 (用户, accessToken, expiresIn)。"""
    user = _find_by_account(db, payload.account.strip())
    # 账号不存在与密码错误返回同一错误码，避免账号探测
    if user is None or not verify_password(payload.password, user.password):
        raise BizError(ErrorCode.ACCOUNT_OR_PASSWORD)

    _assert_active(user)
    _assert_role(user, payload.role)
    return _issue_session(db, user, ip=ip)


def login_by_sms(db: Session, payload: SmsLoginRequest, *, ip: str | None = None) -> tuple[User, str, int]:
    """手机号 + 验证码登录（《功能设计文档》3.1 多方式登录）。"""
    phone = payload.phone.strip()
    sms.verify_code(db, phone, payload.smsCode, SmsScene.LOGIN)

    user = _find_by_account(db, phone)
    if user is None:
        # 验证码正确但没有账号：提示去注册，而不是报告“账号不存在”
        raise BizError(ErrorCode.ACCOUNT_OR_PASSWORD, "该手机号尚未注册，请先注册")

    _assert_active(user)
    _assert_role(user, payload.role)
    return _issue_session(db, user, ip=ip)


def _issue_session(db: Session, user: User, *, ip: str | None) -> tuple[User, str, int]:
    token, expires_in = create_access_token(
        user_id=user.user_id, account=user.account, role=user.role
    )
    user.last_login_at = now()
    _write_log(db, user_id=user.user_id, action="LOGIN", detail=f"{user.role} 登录成功", ip=ip)
    db.commit()
    return user, token, expires_in


def _find_by_account(db: Session, account_value: str) -> User | None:
    """按登录账号、手机号或身份证号匹配（注册时账号=手机号，实名信息仍可登录）。"""
    if not account_value:
        return None
    return db.execute(
        select(User).where(
            or_(
                User.account == account_value,
                User.phone == account_value,
                # idcard 是确定性密文，传明文身份证号时需换算成密文再比对；
                # 演示数据里的医生账号仍是明文，故两种形态一起匹配
                User.idcard.in_(_idcard_candidates(account_value)),
            )
        )
    ).scalars().first()


def _idcard_candidates(account_value: str) -> list[str]:
    """身份证号等值查询候选值；入参不像身份证号时返回空列表（不参与匹配）。"""
    if not is_valid_idcard(account_value):
        return []
    return crypto.equality_candidates(account_value)


def _assert_active(user: User) -> None:
    """停用账号（status=0）不允许登录，与 app.core.deps.get_current_user 保持一致。

    放在口令校验之后：先验密码再报“已被禁用”，避免仅凭账号即可探测账号状态。
    """
    if user.status != 1:
        raise BizError(ErrorCode.FORBIDDEN, "账号已被禁用，请联系管理员")


def _assert_role(user: User, expected: UserRole | str | None) -> None:
    """校验期望登录角色与账号实际角色一致（接口文档 API-01 role 参数）。"""
    if expected is None:
        return
    expected_value = getattr(expected, "value", str(expected))
    if user.role != expected_value:
        raise BizError(ErrorCode.FORBIDDEN, "账号角色与所选登录角色不一致")


def _assert_account_available(db: Session, account_value: str) -> None:
    """账号（手机号）唯一性校验：已注册返回 1002。"""
    exists = db.execute(
        select(User.user_id).where(
            or_(User.account == account_value, User.phone == account_value)
        )
    ).scalars().first()
    if exists:
        raise BizError(ErrorCode.ACCOUNT_EXISTS)


# --------------------------------------------------------------------------- #
# 组装响应 / 操作日志
# --------------------------------------------------------------------------- #


def build_user_info(user: User) -> UserInfo:
    return UserInfo(
        userId=user.user_id,
        name=user.name,
        role=user.role,
        phone=user.phone,
        realNameVerified=bool(user.real_name_verified),
    )


def build_login_data(user: User, access_token: str, expires_in: int) -> LoginData:
    """登录响应 data：accessToken + expiresIn + userInfo（含前端使用的扁平字段）。"""
    return LoginData(
        accessToken=access_token, expiresIn=expires_in, userInfo=build_user_info(user)
    )


def _write_log(
    db: Session,
    *,
    user_id: str | None,
    action: str,
    detail: str | None = None,
    ip: str | None = None,
) -> None:
    """写 t_operation_log：只记动作与脱敏后的摘要，不记密码、验证码等凭据。"""
    db.add(
        OperationLog(
            log_id=next_id(db, OperationLog.log_id, "LOG"),
            user_id=user_id,
            action=action,
            target_type="USER",
            target_id=user_id,
            detail=detail,
            ip=ip,
        )
    )
