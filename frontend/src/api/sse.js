import { getToken } from '@/utils/storage'
import { uuid } from '@/utils/requestId'

const SSE_BASE = import.meta.env.VITE_SSE_BASE_URL || '/api/v1'

/**
 * POST + SSE 流式请求。
 * 原生 EventSource 仅支持 GET，而 AI 接口是 POST 且需携带鉴权头，
 * 因此改用 fetch + ReadableStream 手工解析 text/event-stream。
 *
 * 事件类型（接口文档 API-08）：delta / triageCard / sources / done / error
 *
 * @param {string} url    相对于 baseURL 的路径，如 '/ai/multimodal/messages'
 * @param {object} body   请求体，stream 由本函数统一置为 true
 * @param {object} options { onEvent, onError, signal }
 */
export async function postStream(url, body, options = {}) {
  const { onEvent, onError, signal } = options

  const response = await fetch(`${SSE_BASE}${url}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'text/event-stream',
      Authorization: `Bearer ${getToken() || ''}`,
      'X-Request-Id': uuid(),
      'X-Client': import.meta.env.VITE_CLIENT || 'web-pc',
    },
    body: JSON.stringify({ ...body, stream: true }),
    signal,
  })

  if (!response.ok) {
    const error = new Error(`流式请求失败：HTTP ${response.status}`)
    error.status = response.status
    onError?.(error)
    throw error
  }
  if (!response.body) {
    const error = new Error('当前浏览器不支持流式响应')
    onError?.(error)
    throw error
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''

  try {
    for (;;) {
      const { value, done } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, '\n')

      // SSE 以空行分隔事件块
      let boundary = buffer.indexOf('\n\n')
      while (boundary !== -1) {
        const chunk = buffer.slice(0, boundary)
        buffer = buffer.slice(boundary + 2)
        const event = parseEvent(chunk)
        if (event) onEvent?.(event)
        boundary = buffer.indexOf('\n\n')
      }
    }
  } catch (error) {
    // 主动 abort 不算异常
    if (error.name !== 'AbortError') {
      onError?.(error)
      throw error
    }
  } finally {
    reader.releaseLock()
  }
}

/** 解析单个 SSE 事件块为 { type, data }；data 尝试按 JSON 解析 */
function parseEvent(chunk) {
  let type = 'message'
  const dataLines = []

  for (const line of chunk.split('\n')) {
    if (line.startsWith(':')) continue // 注释/心跳
    if (line.startsWith('event:')) type = line.slice(6).trim()
    else if (line.startsWith('data:')) dataLines.push(line.slice(5).trim())
  }

  const raw = dataLines.join('\n')
  if (!raw) return null

  try {
    return { type, data: JSON.parse(raw) }
  } catch {
    return { type, data: raw }
  }
}
