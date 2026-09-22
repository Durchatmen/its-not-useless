import request from './request'

/**
 * API-22 查询电子病历。
 * startDate / endDate 为就诊日期区间（yyyy-MM-dd），后端按别名接收，可不传。
 */
export function listMedicalRecords({ patientId, startDate, endDate, pageNum = 1, pageSize = 10 } = {}) {
  return request.get('/medical-records', {
    params: { patientId, startDate, endDate, pageNum, pageSize },
  })
}

/** API-23 病历解释（病历解释 Agent，转通俗语言） */
export function interpretRecord({ recordId, textContent }) {
  return request.post('/medical-records/interpretation', { recordId, textContent })
}
