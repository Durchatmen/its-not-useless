import request from './request'

/** API-10 查询排班与号源 */
export function listSchedules({ deptId, doctorId, date, pageNum = 1, pageSize = 20 } = {}) {
  return request.get('/schedules', {
    params: { deptId, doctorId, date, pageNum, pageSize },
  })
}

/** API-11 预约挂号 */
export function createAppointment(payload) {
  return request.post('/appointments', payload)
}

/** API-12 修改挂号（如改期） */
export function updateAppointment(appointmentId, payload) {
  return request.put(`/appointments/${appointmentId}`, payload)
}

/** API-13 取消挂号 */
export function cancelAppointment(appointmentId) {
  return request.delete(`/appointments/${appointmentId}`)
}

/** API-14 挂号历史 */
export function listAppointmentHistory({ pageNum = 1, pageSize = 10, status } = {}) {
  return request.get('/appointments/history', {
    params: { pageNum, pageSize, status },
  })
}

/** API-15 候诊提醒（队列与预计叫号时间） */
export function getAppointmentReminder(appointmentId) {
  return request.get(`/appointments/${appointmentId}/reminder`)
}
