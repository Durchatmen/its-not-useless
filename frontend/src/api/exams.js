import request from './request'

/**
 * 检查列表（后端 summary：检查列表（按日期倒序））。
 * 接口文档 3.8.3 的「查询检查状态」是单条查询，列表走本接口。
 */
export function listExams({ patientId, examStatus, pageNum = 1, pageSize = 10 } = {}) {
  return request.get('/exams', { params: { patientId, examStatus, pageNum, pageSize } })
}

/** API-24 检查注意事项 */
export function getExamPrecautions(examId) {
  return request.get(`/exams/${examId}/precautions`)
}

/** API-25 检查排队进度 */
export function getExamQueue(examId) {
  return request.get(`/exams/${examId}/queue`)
}

/** API-26 检查科室位置 */
export function getExamLocation(examId) {
  return request.get(`/exams/${examId}/location`)
}

/** API-27 查询检查报告 */
export function getExamReport(examId) {
  return request.get(`/exams/${examId}/report`)
}

/** API-28 查询检查状态 */
export function getExamStatus(examId) {
  return request.get(`/exams/${examId}/status`)
}

/** API-29 AI 报告解读（报告 Agent，转通俗语言并提示风险等级） */
export function analyzeExamReport(examId, payload = {}) {
  return request.post(`/exams/${examId}/report/analysis`, payload)
}
