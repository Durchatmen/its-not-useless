import request from './request'

/** API-32 医保咨询（医保知识库 RAG 问答） */
export function consultInsurance({ question, sessionId, patientId }) {
  return request.post('/insurance/consult', { question, sessionId, patientId })
}
