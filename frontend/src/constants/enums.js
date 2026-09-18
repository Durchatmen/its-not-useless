/**
 * 通用枚举字典 —— 对应《接口文档》2.6
 */

/** 用户角色。注：接口文档仅定义三类；需求分析 9.1 另含"运营"角色，后台端使用 */
export const ROLE = {
  PATIENT: 'PATIENT',
  DOCTOR: 'DOCTOR',
  ADMIN: 'ADMIN',
}

export const ROLE_LABEL = {
  [ROLE.PATIENT]: '患者',
  [ROLE.DOCTOR]: '医生',
  [ROLE.ADMIN]: '系统管理员',
}

/** 与本人关系 */
export const RELATION = {
  SELF: 'SELF',
  SPOUSE: 'SPOUSE',
  CHILD: 'CHILD',
  PARENT: 'PARENT',
  OTHER: 'OTHER',
}

export const RELATION_LABEL = {
  [RELATION.SELF]: '本人',
  [RELATION.SPOUSE]: '配偶',
  [RELATION.CHILD]: '子女',
  [RELATION.PARENT]: '父母',
  [RELATION.OTHER]: '其他',
}

/** 挂号状态 */
export const APPOINTMENT_STATUS = {
  BOOKED: 'BOOKED',
  CHECKED_IN: 'CHECKED_IN',
  FINISHED: 'FINISHED',
  CANCELED: 'CANCELED',
}

export const APPOINTMENT_STATUS_LABEL = {
  [APPOINTMENT_STATUS.BOOKED]: '已预约待就诊',
  [APPOINTMENT_STATUS.CHECKED_IN]: '已取号',
  [APPOINTMENT_STATUS.FINISHED]: '已完成',
  [APPOINTMENT_STATUS.CANCELED]: '已取消',
}

/** Element Plus tag 类型，供列表直接绑定 */
export const APPOINTMENT_STATUS_TAG = {
  [APPOINTMENT_STATUS.BOOKED]: 'primary',
  [APPOINTMENT_STATUS.CHECKED_IN]: 'warning',
  [APPOINTMENT_STATUS.FINISHED]: 'success',
  [APPOINTMENT_STATUS.CANCELED]: 'info',
}

/** 检查状态 */
export const EXAM_STATUS = {
  WAIT_PAY: 'WAIT_PAY',
  WAIT_EXAM: 'WAIT_EXAM',
  WAIT_REPORT: 'WAIT_REPORT',
  REPORTED: 'REPORTED',
}

export const EXAM_STATUS_LABEL = {
  [EXAM_STATUS.WAIT_PAY]: '待缴费',
  [EXAM_STATUS.WAIT_EXAM]: '待检查',
  [EXAM_STATUS.WAIT_REPORT]: '待报告',
  [EXAM_STATUS.REPORTED]: '已报告',
}

/** 账单类型与状态 */
export const BILL_TYPE = {
  REGISTRATION: 'REGISTRATION',
  TREATMENT: 'TREATMENT',
}

export const BILL_TYPE_LABEL = {
  [BILL_TYPE.REGISTRATION]: '挂号缴费',
  [BILL_TYPE.TREATMENT]: '就诊缴费',
}

export const BILL_STATUS = {
  UNPAID: 'UNPAID',
  PAID: 'PAID',
  REFUNDED: 'REFUNDED',
}

export const BILL_STATUS_LABEL = {
  [BILL_STATUS.UNPAID]: '待缴费',
  [BILL_STATUS.PAID]: '已缴费',
  [BILL_STATUS.REFUNDED]: '已退费',
}

/** 支付渠道 */
export const PAY_CHANNEL = {
  WECHAT: 'WECHAT',
  ALIPAY: 'ALIPAY',
}

export const PAY_CHANNEL_LABEL = {
  [PAY_CHANNEL.WECHAT]: '微信支付',
  [PAY_CHANNEL.ALIPAY]: '支付宝',
}

/** AI 输入类型 */
export const AI_INPUT_TYPE = {
  TEXT: 'TEXT',
  VOICE: 'VOICE',
  IMAGE: 'IMAGE',
}

/** 分诊卡片按钮动作 */
export const TRIAGE_ACTION = {
  GO_REGISTER: 'GO_REGISTER',
}
