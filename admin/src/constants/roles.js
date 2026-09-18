/**
 * 后台端角色。
 * 注意：《接口文档》2.6 的 role 字典只有 PATIENT / DOCTOR / ADMIN，
 * 而《需求分析》9.1 权限矩阵另有"运营"角色，此处先按 OPERATOR 占位，
 * 待管理端接口文档确定后统一。
 */
export const ADMIN_ROLE = {
  ADMIN: 'ADMIN',
  OPERATOR: 'OPERATOR',
}

export const ADMIN_ROLE_LABEL = {
  [ADMIN_ROLE.ADMIN]: '系统管理员',
  [ADMIN_ROLE.OPERATOR]: '运营',
}

/** 各页面允许的角色，空表示登录即可 */
export const MENU = [
  { name: 'Dashboard', icon: '📊', text: '概览', roles: [] },
  { name: 'DeptList', icon: '🏥', text: '科室维护', roles: [ADMIN_ROLE.ADMIN] },
  { name: 'DoctorList', icon: '👨‍⚕️', text: '医生维护', roles: [ADMIN_ROLE.ADMIN] },
  { name: 'ScheduleList', icon: '📅', text: '排班维护', roles: [ADMIN_ROLE.ADMIN] },
  { name: 'FloorMap', icon: '🗺️', text: '楼层平面图', roles: [ADMIN_ROLE.ADMIN] },
  { name: 'UserList', icon: '👥', text: '用户管理', roles: [ADMIN_ROLE.ADMIN] },
  { name: 'RoleAssign', icon: '🔑', text: '权限分配', roles: [ADMIN_ROLE.ADMIN] },
  { name: 'KnowledgeList', icon: '📚', text: '知识库维护', roles: [ADMIN_ROLE.ADMIN] },
  { name: 'KnowledgeUpload', icon: '⬆️', text: '知识库导入', roles: [ADMIN_ROLE.ADMIN] },
  { name: 'SessionLog', icon: '💬', text: '会话日志', roles: [] },
  { name: 'Intervene', icon: '🆘', text: '人工兜底', roles: [ADMIN_ROLE.OPERATOR] },
  { name: 'QueueMonitor', icon: '⏱️', text: '排队监控', roles: [] },
  { name: 'OperationLog', icon: '📝', text: '操作日志', roles: [] },
]

export function hasRole(userRole, roles) {
  if (!roles || !roles.length) return true
  return roles.includes(userRole)
}
