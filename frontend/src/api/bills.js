import request from './request'

/** API-16 查询账单列表 */
export function listBills({ billType, billStatus, pageNum = 1, pageSize = 10 } = {}) {
  return request.get('/bills', {
    params: { billType, billStatus, pageNum, pageSize },
  })
}

/** API-17 诊间结算 */
export function settleBill(billId, payload = {}) {
  return request.post(`/bills/${billId}/settle`, payload)
}
