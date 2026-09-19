import request from './request'

/* 登录与账号 */

export function adminLogin({ account, password }) {
  return request.post('/admin/auth/login', { account, password })
}

export function adminLogout() {
  return request.post('/admin/auth/logout')
}

export function getAdminProfile() {
  return request.get('/admin/auth/profile')
}
