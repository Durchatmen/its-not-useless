import request from './request'

/** API-30 查询当前处方 */
export function getCurrentPrescription({ patientId } = {}) {
  return request.get('/prescriptions/current', { params: { patientId } })
}

/** API-31 创建用药提醒 */
export function createMedicationReminder(payload) {
  return request.post('/medication-reminders', payload)
}
