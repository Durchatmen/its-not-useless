import request from './request'

/* AI 会话日志查看与人工兜底介入（管理员 / 运营） */

export function listAiSessions(params) {
  return request.get('/admin/ai/sessions', { params })
}

export function getAiSessionDetail(sessionId) {
  return request.get(`/admin/ai/sessions/${sessionId}`)
}

/** 人工兜底介入：标记会话并接管回复 */
export function interveneSession(sessionId, payload) {
  return request.post(`/admin/ai/sessions/${sessionId}/intervene`, payload)
}
