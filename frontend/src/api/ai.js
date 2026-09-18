import request from './request'
import { postStream } from './sse'

/**
 * API-08 多模态预诊分诊（非流式）
 * @param {object} payload { sessionId?, patientId?, inputType, textContent?,
 *                           audioData?, audioFormat?, imageData? }
 */
export function sendMessage(payload) {
  return request.post('/ai/multimodal/messages', { ...payload, stream: false })
}

/**
 * API-08 多模态预诊分诊（流式 SSE）
 * stream=true 时后端不再返回统一 JSON 信封，由 sse.js 逐事件回调
 * @param {object} payload 同上，stream 由 postStream 置为 true
 * @param {object} handlers { onEvent, onError, signal }
 */
export function sendMessageStream(payload, handlers) {
  return postStream('/ai/multimodal/messages', payload, handlers)
}

/** API-09 查询会话历史 */
export function getSessionHistory(sessionId, { pageNum = 1, pageSize = 20 } = {}) {
  return request.get(`/ai/multimodal/sessions/${sessionId}`, {
    params: { pageNum, pageSize },
  })
}
