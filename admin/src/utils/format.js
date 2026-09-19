/**
 * 时间格式 yyyy-MM-dd HH:mm:ss —— 《接口文档》2.1 全局约定（东八区）
 */
export function formatDateTime(value) {
  if (!value) return ''
  const date = value instanceof Date ? value : new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)
  const pad = (n) => String(n).padStart(2, '0')
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ` +
    `${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
  )
}

export function formatDate(value) {
  return formatDateTime(value).slice(0, 10)
}

/**
 * 金额：单位元、保留两位小数、数字类型 —— 《接口文档》2.1
 * 返回数字以便参与计算，展示时交给 formatMoneyText
 */
export function formatMoney(value) {
  const num = Number(value)
  return Number.isFinite(num) ? Number(num.toFixed(2)) : 0
}

export function formatMoneyText(value) {
  return `¥${formatMoney(value).toFixed(2)}`
}
