import { ref, watch } from 'vue'
import { defineStore } from 'pinia'

import { getPreference, setPreference } from '@/utils/storage'

/**
 * 全局偏好：大字模式 / 高对比度（需求分析 F4.2 无障碍适配）
 * 以 html 上的 class 驱动，样式见 styles/theme.less
 */
export const useAppStore = defineStore('app', () => {
  const stored = getPreference()

  const largeFont = ref(Boolean(stored.largeFont))
  const highContrast = ref(Boolean(stored.highContrast))

  function applyToDocument() {
    const root = document.documentElement
    root.classList.toggle('large-font', largeFont.value)
    root.classList.toggle('high-contrast', highContrast.value)
  }

  function toggleLargeFont(value) {
    largeFont.value = typeof value === 'boolean' ? value : !largeFont.value
  }

  function toggleHighContrast(value) {
    highContrast.value = typeof value === 'boolean' ? value : !highContrast.value
  }

  watch(
    [largeFont, highContrast],
    () => {
      applyToDocument()
      setPreference({ largeFont: largeFont.value, highContrast: highContrast.value })
    },
    { immediate: true },
  )

  return { largeFont, highContrast, toggleLargeFont, toggleHighContrast }
})
