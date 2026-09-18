import { ref } from 'vue'

import { sendMessageStream } from '@/api/ai'
import { useChatStore } from '@/stores/chat'

/**
 * AI 流式对话。
 * 把 API-08 的 SSE 事件映射到 chat store，供会话页边收边渲染。
 * 事件：delta（增量文本）/ triageCard（分诊卡片）/ sources（引用来源）/ done / error
 */
export function useSse() {
  const chat = useChatStore()
  const error = ref('')
  let controller = null

  function handleEvent(event) {
    switch (event.type) {
      case 'delta':
        chat.appendDelta(typeof event.data === 'string' ? event.data : event.data?.text || '')
        break
      case 'triageCard':
        chat.setTriageCard(event.data)
        break
      case 'sources':
        chat.setSources(Array.isArray(event.data) ? event.data : event.data?.sources)
        break
      case 'done':
        // done 事件可能回带 sessionId / recognizedText / disclaimer / nextQuestion
        chat.finish(typeof event.data === 'object' && event.data ? event.data : {})
        break
      case 'error':
        chat.fail(typeof event.data === 'string' ? event.data : event.data?.message)
        break
      default:
        break
    }
  }

  /**
   * 发起一轮对话
   * @param {object} payload { inputType, textContent?, audioData?, imageData?, patientId? }
   */
  async function send(payload) {
    error.value = ''
    chat.pushUserMessage(payload)
    chat.beginBotMessage()

    controller = new AbortController()
    try {
      await sendMessageStream(
        { ...payload, sessionId: chat.sessionId || undefined },
        { onEvent: handleEvent, signal: controller.signal },
      )
    } catch (err) {
      error.value = err?.message || 'AI 服务繁忙，请稍后重试'
      chat.fail(error.value)
      throw err
    } finally {
      controller = null
      // 兜底：后端未推 done 时也要收尾，避免气泡一直转圈
      if (chat.streaming) chat.finish()
    }
  }

  function abort() {
    controller?.abort()
    controller = null
    if (chat.streaming) chat.finish()
  }

  return { send, abort, error }
}
