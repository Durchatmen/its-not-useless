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

/** 登录态 / Token / 角色 —— 技术选型指定由 Pinia 承载 */
export const useUserStore = defineStore('user', () => {
  const token = ref(getToken() || '')
  const profile = ref(getStoredUser())

  const isLogged = computed(() => Boolean(token.value))
  const role = computed(() => profile.value?.role || '')
  const userId = computed(() => profile.value?.userId || '')
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
    const data = await authApi.login(payload)
    setAuth(data)
    return data
  }

  function logout() {
    token.value = ''
    profile.value = null
    clearToken()
    clearStoredUser()
  }

  return { token, profile, isLogged, role, userId, displayName, setAuth, login, logout }
})
