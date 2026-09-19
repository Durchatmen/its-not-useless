/**
 * 错误码表 —— 对应《智慧医疗AI辅助系统接口文档》2.5 通用错误码表
 */
export const ERROR_CODE = {
  SUCCESS: 0,
  ACCOUNT_OR_PASSWORD: 1001, // 账号或密码错误
  ACCOUNT_EXISTS: 1002, // 账号已存在
  SMS_CODE_INVALID: 1003, // 短信验证码错误或已过期
  REAL_NAME_FAILED: 1004, // 实名认证失败（姓名与身份证号不一致）
  NO_SCHEDULE: 2001, // 号源不足或已被占用
  APPOINTMENT_INVALID: 2002, // 挂号单不存在或当前状态不允许该操作
  PATIENT_INVALID: 2003, // 就诊人信息校验失败
  BILL_INVALID: 3001, // 账单不存在或已缴费
  PAY_CHANNEL_FAILED: 3002, // 支付渠道（微信/支付宝）下单失败
  PAY_TIMEOUT: 3003, // 支付超时或用户取消支付
  PARAM_INVALID: 4001, // 参数校验失败
  UNAUTHORIZED: 4002, // 未登录或 Token 无效/过期
  FORBIDDEN: 4003, // 无权访问该资源
  HIS_FAILED: 5001, // 医院HIS系统调用失败
  LLM_FAILED: 5002, // 大模型服务调用失败或超时
  RAG_FAILED: 5003, // 知识库检索失败
  AMAP_FAILED: 5004, // 高德地图服务调用失败
  INTERNAL: 9999, // 系统内部错误
}

/** 错误码 → 前端提示文案 */
const MESSAGES = {
  [ERROR_CODE.ACCOUNT_OR_PASSWORD]: '账号或密码错误',
  [ERROR_CODE.ACCOUNT_EXISTS]: '账号已存在',
  [ERROR_CODE.SMS_CODE_INVALID]: '短信验证码错误或已过期',
  [ERROR_CODE.REAL_NAME_FAILED]: '实名认证失败，请核对姓名与身份证号',
  [ERROR_CODE.NO_SCHEDULE]: '号源不足或已被占用，请更换时段',
  [ERROR_CODE.APPOINTMENT_INVALID]: '挂号单不存在或当前状态不允许该操作',
  [ERROR_CODE.PATIENT_INVALID]: '就诊人信息校验失败',
  [ERROR_CODE.BILL_INVALID]: '账单不存在或已缴费',
  [ERROR_CODE.PAY_CHANNEL_FAILED]: '支付下单失败，请稍后重试',
  [ERROR_CODE.PAY_TIMEOUT]: '支付超时或已取消',
  [ERROR_CODE.PARAM_INVALID]: '参数校验失败',
  [ERROR_CODE.UNAUTHORIZED]: '登录已过期，请重新登录',
  [ERROR_CODE.FORBIDDEN]: '无权访问该资源',
  [ERROR_CODE.HIS_FAILED]: '医院系统繁忙，请稍后重试',
  [ERROR_CODE.LLM_FAILED]: 'AI 服务繁忙，请稍后重试',
  [ERROR_CODE.RAG_FAILED]: '知识库检索失败，请稍后重试',
  [ERROR_CODE.AMAP_FAILED]: '地图服务不可用',
  [ERROR_CODE.INTERNAL]: '系统内部错误',
}

export function errorMessage(code) {
  return MESSAGES[code] || '请求失败，请稍后重试'
}

/** 业务错误对象，便于调用方按 code 分支处理 */
export class ApiError extends Error {
  constructor(code, message) {
    super(message || errorMessage(code))
    this.name = 'ApiError'
    this.code = code
  }
}
