import request from './request'

/** API-22 查询电子病历 */
export function listMedicalRecords({ patientId, pageNum = 1, pageSize = 10 } = {}) {
  return request.get('/medical-records', {
    params: { patientId, pageNum, pageSize },
  })
}

/** API-23 病历解释（病历解释 Agent，转通俗语言） */
export function interpretRecord({ recordId, textContent }) {
  return request.post('/medical-records/interpretation', { recordId, textContent })
}
