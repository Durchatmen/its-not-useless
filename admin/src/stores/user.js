import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import * as authApi from '@/api/auth'
import {
  clearStoredUser,
  clearToken,
  getStoredUser,
  getToken,
  setStoredUser,
  setToken,
} from '@/utils/storage'

/** 后台端登录态：独立 Token、独立鉴权（需求分析 9.3） */
export const useAdminUserStore = defineStore('adminUser', () => {
  const token = ref(getToken() || '')
  const profile = ref(getStoredUser())

  const isLogged = computed(() => Boolean(token.value))
  const role = computed(() => profile.value?.role || '')
  const displayName = computed(() => profile.value?.name || '')

  function setAuth(payload) {
    const { accessToken, ...rest } = payload || {}
    if (accessToken) {
      token.value = accessToken
      setToken(accessToken)
    }
    if (rest && Object.keys(rest).length) {
      profile.value = { ...(profile.value || {}), ...rest }
      setStoredUser(profile.value)
    }
  }

  async function login(payload) {
    const data = await authApi.adminLogin(payload)
    setAuth(data)
    return data
  }

  async function logout() {
    try {
      await authApi.adminLogout()
    } catch {
      // 登出接口失败不阻塞本地清理
    }
    token.value = ''
    profile.value = null
    clearToken()
    clearStoredUser()
  }

  return { token, profile, isLogged, role, displayName, setAuth, login, logout }
})
