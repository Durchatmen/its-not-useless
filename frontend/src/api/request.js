import axios from 'axios'
import { ElMessage } from 'element-plus'

import { getToken, clearToken, clearStoredUser } from '@/utils/storage'
import { uuid } from '@/utils/requestId'
import { ApiError, ERROR_CODE, errorMessage } from '@/utils/errorCode'

const request = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL,
  timeout: 20000,
})

/** 防止并发 4002 反复跳转 */
let redirecting = false

async function redirectToLogin() {
  if (redirecting) return
  redirecting = true
  clearToken()
  clearStoredUser()
  try {
    // 动态引入避免 request.js ↔ router 的循环依赖
    const { default: router } = await import('@/router')
    const current = router.currentRoute.value
    if (current.name !== 'Login') {
      await router.replace({ name: 'Login', query: { redirect: current.fullPath } })
    }
  } finally {
    redirecting = false
  }
}

/* ---------------- 请求拦截：注入鉴权与链路头（接口文档 2.2 / 2.3）---------------- */
request.interceptors.request.use(
  (config) => {
    const token = getToken()
    if (token) config.headers.Authorization = `Bearer ${token}`
    config.headers['X-Request-Id'] = config.headers['X-Request-Id'] || uuid()
    config.headers['X-Client'] = import.meta.env.VITE_CLIENT || 'web-pc'
    return config
  },
  (error) => Promise.reject(error),
)

/* ---------------- 响应拦截：解统一信封（接口文档 2.4）---------------- */
request.interceptors.response.use(
  (response) => {
    const body = response.data

    // 非信封响应（如文件流）原样返回
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
    // HTTP 层错误：401 视同 Token 失效
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
