import request from './request'

/** API-01 用户登录 */
export function login({ account, password, role }) {
  return request.post('/auth/login', { account, password, role })
}

/** API-02 用户注册 */
export function register(payload) {
  return request.post('/auth/register', payload)
}

/** API-03 发送短信验证码 */
export function sendSmsCode({ phone, scene }) {
  return request.post('/auth/sms-code', { phone, scene })
}
