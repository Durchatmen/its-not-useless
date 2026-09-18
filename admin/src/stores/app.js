import { ref } from 'vue'
import { defineStore } from 'pinia'

import { getPreference, setPreference } from '@/utils/storage'

/** 后台端全局状态：侧边栏折叠、大字模式、高对比度 */
export const useAdminAppStore = defineStore('adminApp', () => {
  const stored = getPreference()

  const sidebarCollapsed = ref(Boolean(stored.sidebarCollapsed))
  const largeFont = ref(Boolean(stored.largeFont))
  const highContrast = ref(Boolean(stored.highContrast))

  function persist() {
    const root = document.documentElement
    root.classList.toggle('large-font', largeFont.value)
    root.classList.toggle('high-contrast', highContrast.value)

    setPreference({
      sidebarCollapsed: sidebarCollapsed.value,
      largeFont: largeFont.value,
      highContrast: highContrast.value,
    })
  }

  function toggleSidebar() {
    sidebarCollapsed.value = !sidebarCollapsed.value
    persist()
  }

  function toggleLargeFont() {
    largeFont.value = !largeFont.value
    persist()
  }

  function toggleHighContrast() {
    highContrast.value = !highContrast.value
    persist()
  }

  /** 应用启动时恢复偏好 */
  function init() {
    persist()
  }

  return {
    sidebarCollapsed, largeFont, highContrast,
    toggleSidebar, toggleLargeFont, toggleHighContrast, init,
  }
})
