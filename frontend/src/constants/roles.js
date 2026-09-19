import { ROLE } from './enums'

/** 可访问患者端前端的角色（需求分析 9.1 权限矩阵） */
export const PATIENT_SIDE_ROLES = [ROLE.PATIENT]

/** 可访问管理/运营后台的角色 */
export const ADMIN_SIDE_ROLES = [ROLE.ADMIN, 'OPERATOR']

/** 路由 meta.roles 为空时表示登录即可访问 */
export function hasRole(userRole, roles) {
  if (!roles || !roles.length) return true
  return roles.includes(userRole)
}
