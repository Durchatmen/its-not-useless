import request from './request'

/* 科室 / 医生 / 排班 / 楼层平面图（管理员） */

export function listDepartments(params) {
  return request.get('/admin/departments', { params })
}
export function createDepartment(payload) {
  return request.post('/admin/departments', payload)
}
export function updateDepartment(deptId, payload) {
  return request.put(`/admin/departments/${deptId}`, payload)
}
export function removeDepartment(deptId) {
  return request.delete(`/admin/departments/${deptId}`)
}

export function listDoctors(params) {
  return request.get('/admin/doctors', { params })
}
export function createDoctor(payload) {
  return request.post('/admin/doctors', payload)
}
export function updateDoctor(doctorId, payload) {
  return request.put(`/admin/doctors/${doctorId}`, payload)
}

export function listSchedules(params) {
  return request.get('/admin/schedules', { params })
}
export function createSchedule(payload) {
  return request.post('/admin/schedules', payload)
}

/** 楼层平面图：CAD 转 GeoJSON 后上传（环境搭建方案 §6.6） */
export function getFloorMap(floor) {
  return request.get(`/admin/floors/${floor}`)
}
export function uploadFloorMap(floor, payload) {
  return request.post(`/admin/floors/${floor}`, payload)
}
