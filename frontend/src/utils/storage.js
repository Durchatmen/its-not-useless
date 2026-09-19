const TOKEN_KEY = 'hospital_ai_token'
const USER_KEY = 'hospital_ai_user'
const PATIENT_KEY = 'hospital_ai_current_patient'
const PREF_KEY = 'hospital_ai_preference'

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

export function getCurrentPatientId() {
  return localStorage.getItem(PATIENT_KEY) || ''
}
export function setCurrentPatientId(patientId) {
  localStorage.setItem(PATIENT_KEY, patientId)
}
export function clearCurrentPatientId() {
  localStorage.removeItem(PATIENT_KEY)
}

/** 无障碍偏好：大字模式 / 高对比度 */
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
