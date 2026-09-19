import request from './request'

/* 操作日志与系统监控 */

export function listOperationLogs(params) {
  return request.get('/admin/logs', { params })
}

export function getSystemMetrics() {
  return request.get('/admin/metrics')
}
