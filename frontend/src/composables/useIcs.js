import { createEvents } from 'ics'

/**
 * 用药提醒导出日历（技术选型指定 ics）。
 * 用于用药计划页的"添加到日历"按钮。
 */
export function useIcs() {
  /** 'HH:mm' 转 ics 的 [hour, minute] */
  function parseTime(timeText) {
    const [hour, minute] = String(timeText || '08:00').split(':')
    return [Number(hour) || 8, Number(minute) || 0]
  }

  /**
   * 把服药计划转成 .ics 并触发下载
   * @param {Array} reminders [{ title, date, time, durationMinutes, description, location }]
   * @param {string} filename
   */
  function exportReminders(reminders = [], filename = '用药提醒.ics') {
    const events = reminders.map((item) => {
      const base = item.date ? new Date(item.date) : new Date()
      const [hour, minute] = parseTime(item.time)
      return {
        start: [base.getFullYear(), base.getMonth() + 1, base.getDate(), hour, minute],
        duration: { minutes: item.durationMinutes || 15 },
        title: item.title || '用药提醒',
        description: item.description || '',
        location: item.location || '',
        alarms: [{ action: 'display', trigger: { minutes: 10, before: true } }],
      }
    })

    return new Promise((resolve, reject) => {
      createEvents(events, (error, value) => {
        if (error) {
          reject(error)
          return
        }
        const blob = new Blob([value], { type: 'text/calendar;charset=utf-8' })
        const link = document.createElement('a')
        link.href = URL.createObjectURL(blob)
        link.download = filename
        link.click()
        URL.revokeObjectURL(link.href)
        resolve(value)
      })
    })
  }

  return { exportReminders }
}
