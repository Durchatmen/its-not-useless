import { storeToRefs } from 'pinia'

import { useAppStore } from '@/stores/app'

/** 大字模式 / 高对比度（需求分析 F4.2 无障碍） */
export function useAccessibility() {
  const appStore = useAppStore()
  const { largeFont, highContrast } = storeToRefs(appStore)

  return {
    largeFont,
    highContrast,
    toggleLargeFont: appStore.toggleLargeFont,
    toggleHighContrast: appStore.toggleHighContrast,
  }
}
