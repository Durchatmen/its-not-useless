/** 生成链路追踪 ID（《接口文档》2.3 统一请求头 X-Request-Id） */
export function uuid() {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID()
  // 降级：非安全上下文（如 http 内网访问）下 crypto.randomUUID 不可用
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0
    const v = c === 'x' ? r : (r & 0x3) | 0x8
    return v.toString(16)
  })
}
