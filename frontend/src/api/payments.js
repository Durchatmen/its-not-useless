import request from './request'

/** API-18 发起支付 */
export function createPayment({ billId, channel, amount }) {
  return request.post('/payments', { billId, channel, amount })
}

/** API-19 查询支付结果 */
export function getPayment(paymentId) {
  return request.get(`/payments/${paymentId}`)
}
