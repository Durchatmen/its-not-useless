import axios from 'axios'
import { ElMessage } from 'element-plus'

import { clearStoredUser, clearToken, getToken } from '@/utils/storage'
import { uuid } from '@/utils/requestId'
import { ApiError, ERROR_CODE, errorMessage } from '@/utils/errorCode'

/**
 * 后台端独立的 Axios 实例（独立鉴权、独立 Token）。
 * 统一信封 / 错误码沿用《接口文档》2.4、2.5。
 */
const request = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL,
  timeout: 30000,
})

let redirecting = false

async function redirectToLogin() {
  if (redirecting) return
  redirecting = true
  clearToken()
  clearStoredUser()
  try {
    const { default: router } = await import('@/router')
    const current = router.currentRoute.value
    if (current.name !== 'AdminLogin') {
      await router.replace({ name: 'AdminLogin', query: { redirect: current.fullPath } })
    }
  } finally {
    redirecting = false
  }
}

request.interceptors.request.use(
  (config) => {
    const token = getToken()
    if (token) config.headers.Authorization = `Bearer ${token}`
    config.headers['X-Request-Id'] = config.headers['X-Request-Id'] || uuid()
    config.headers['X-Client'] = import.meta.env.VITE_CLIENT || 'admin-pc'
    return config
  },
  (error) => Promise.reject(error),
)

request.interceptors.response.use(
  (response) => {
    const body = response.data
    if (!body || typeof body !== 'object' || !('code' in body)) return body

    if (body.code === ERROR_CODE.SUCCESS) return body.data

    if (body.code === ERROR_CODE.UNAUTHORIZED) {
      ElMessage.error(errorMessage(ERROR_CODE.UNAUTHORIZED))
      redirectToLogin()
      return Promise.reject(new ApiError(body.code, body.message))
    }

    const message = body.message || errorMessage(body.code)
    ElMessage.error(message)
    return Promise.reject(new ApiError(body.code, message))
  },
  (error) => {
    if (error.response?.status === 401) {
      ElMessage.error(errorMessage(ERROR_CODE.UNAUTHORIZED))
      redirectToLogin()
      return Promise.reject(new ApiError(ERROR_CODE.UNAUTHORIZED))
    }

    const message =
      error.code === 'ECONNABORTED'
        ? '请求超时，请稍后重试'
        : error.response?.status === 404
          ? '接口不存在'
          : '网络异常，请检查网络连接'

    ElMessage.error(message)
    return Promise.reject(new ApiError(ERROR_CODE.INTERNAL, message))
  },
)

export default request
