import request from './request'

/** API-04 查询就诊人列表 */
export function listPatients() {
  return request.get('/patients')
}

/** API-05 添加就诊人 */
export function createPatient(payload) {
  return request.post('/patients', payload)
}

/** API-06 修改就诊人 */
export function updatePatient(patientId, payload) {
  return request.put(`/patients/${patientId}`, payload)
}

/** API-07 删除就诊人 */
export function removePatient(patientId) {
  return request.delete(`/patients/${patientId}`)
}
