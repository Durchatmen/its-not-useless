/**
 * 就诊人相关枚举 —— 取值与《接口文档》2.6 一致，也与后端
 * backend/app/schemas/patient.py 的 GenderValue / RelationValue 一一对应。
 *
 * 注意：性别用 M / F，不是 MALE / FEMALE（文档口径）。
 */
import { RELATION, RELATION_LABEL } from './enums'

export const GENDER = {
  M: 'M',
  F: 'F',
}

export const GENDER_LABEL = {
  [GENDER.M]: '男',
  [GENDER.F]: '女',
}

/** 供 el-select / el-radio-group 直接 v-for，顺序固定，不依赖对象键序 */
export const GENDER_OPTIONS = [
  { value: GENDER.M, label: GENDER_LABEL[GENDER.M] },
  { value: GENDER.F, label: GENDER_LABEL[GENDER.F] },
]

export { RELATION, RELATION_LABEL }

export const RELATION_OPTIONS = [
  { value: RELATION.SELF, label: RELATION_LABEL[RELATION.SELF] },
  { value: RELATION.SPOUSE, label: RELATION_LABEL[RELATION.SPOUSE] },
  { value: RELATION.CHILD, label: RELATION_LABEL[RELATION.CHILD] },
  { value: RELATION.PARENT, label: RELATION_LABEL[RELATION.PARENT] },
  { value: RELATION.OTHER, label: RELATION_LABEL[RELATION.OTHER] },
]
