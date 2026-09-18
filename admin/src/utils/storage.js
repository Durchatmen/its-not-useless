/**
 * 后台端使用独立的存储键，与患者端互不影响（需求分析 9.3：后台端独立鉴权）
 */
const TOKEN_KEY = 'hospital_ai_admin_token'
const USER_KEY = 'hospital_ai_admin_user'
const PREF_KEY = 'hospital_ai_admin_preference'

export function getToken() {
  return localStorage.getItem(TOKEN_KEY) || ''
}
export function setToken(token) {
  localStorage.setItem(TOKEN_KEY, token)
}
export function clearToken() {
  localStorage.removeItem(TOKEN_KEY)
}

export function getStoredUser() {
  try {
    return JSON.parse(localStorage.getItem(USER_KEY) || 'null')
  } catch {
    return null
  }
}
export function setStoredUser(user) {
  localStorage.setItem(USER_KEY, JSON.stringify(user))
}
export function clearStoredUser() {
  localStorage.removeItem(USER_KEY)
}

export function getPreference() {
  try {
    return JSON.parse(localStorage.getItem(PREF_KEY) || '{}')
  } catch {
    return {}
  }
}
export function setPreference(pref) {
  localStorage.setItem(PREF_KEY, JSON.stringify(pref))
}
