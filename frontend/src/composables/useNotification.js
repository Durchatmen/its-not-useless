import { ref } from 'vue'
import { ElNotification } from 'element-plus'

/**
 * 浏览器通知封装（技术选型：Notification API，用于叫号、报告、用药提醒）。
 * 未授权 / 浏览器不支持时降级为页面内提示，不得让提醒静默丢失（F4.4）。
 */
export function useNotification() {
  const supported = typeof window !== 'undefined' && 'Notification' in window
  const permission = ref(supported ? Notification.permission : 'unsupported')

  async function requestPermission() {
    if (!supported) return 'unsupported'
    permission.value = await Notification.requestPermission()
    return permission.value
  }

  /**
   * 发送通知：优先系统通知，降级为页面内通知
   * @param {object} options { title, body, tag, data, onClick }
   */
  function notify({ title, body, tag, data, onClick } = {}) {
    if (supported && permission.value === 'granted') {
      const instance = new Notification(title, { body, tag, data })
      instance.onclick = () => {
        window.focus()
        onClick?.()
      }
      return instance
    }

    // 降级：页面内通知
    return ElNotification({ title, message: body, type: 'info', onClick })
  }

  return { supported, permission, requestPermission, notify }
}
