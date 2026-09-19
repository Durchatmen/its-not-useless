import request from './request'

/* 排队进度监控 */

export function listQueues(params) {
  return request.get('/admin/queues', { params })
}
