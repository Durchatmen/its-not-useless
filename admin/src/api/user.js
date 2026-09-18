import request from './request'

/* 用户管理与权限分配（管理员） */

export function listUsers(params) {
  return request.get('/admin/users', { params })
}
export function updateUserStatus(userId, payload) {
  return request.put(`/admin/users/${userId}/status`, payload)
}

export function listRoles() {
  return request.get('/admin/roles')
}
export function assignUserRoles(userId, payload) {
  return request.put(`/admin/users/${userId}/roles`, payload)
}
