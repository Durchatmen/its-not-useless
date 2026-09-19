import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import { uuid } from '@/utils/requestId'

/**
 * AI 会话上下文 —— 技术选型指定由 Pinia 承载。
 * 消息结构：{ id, role: 'user'|'bot', inputType, textContent, reply,
 *             triageCard, riskWarning, sources, disclaimer, nextQuestion, streaming }
 */
export const useChatStore = defineStore('chat', () => {
  const sessionId = ref('')
  const messages = ref([])
  const streaming = ref(false)
  /** 当前正在流式输出的机器人消息 id */
  const streamingId = ref('')

  const lastMessage = computed(() => messages.value[messages.value.length - 1] || null)

  function pushUserMessage({ inputType = 'TEXT', textContent = '', audioData, imageData }) {
    const message = {
      id: uuid(),
      role: 'user',
      inputType,
      textContent,
      audioData,
      imageData,
      createTime: new Date(),
    }
    messages.value.push(message)
    return message
  }

  /** 开启一条空的机器人消息，等待 delta 逐字填充 */
  function beginBotMessage() {
    const message = {
      id: uuid(),
      role: 'bot',
      reply: '',
      triageCard: null,
      riskWarning: '',
      sources: [],
      disclaimer: '',
      nextQuestion: '',
      streaming: true,
      createTime: new Date(),
    }
    messages.value.push(message)
    streamingId.value = message.id
    streaming.value = true
    return message
  }

  function patchStreamingMessage(patch) {
    const target = messages.value.find((item) => item.id === streamingId.value)
    if (target) Object.assign(target, patch)
    return target
  }

  function appendDelta(text) {
    const target = messages.value.find((item) => item.id === streamingId.value)
    if (target) target.reply += text
  }

  function setTriageCard(card) {
    patchStreamingMessage({ triageCard: card })
  }

  function setSources(sources) {
    patchStreamingMessage({ sources: sources || [] })
  }

  function finish(payload = {}) {
    patchStreamingMessage({ ...payload, streaming: false })
    streaming.value = false
    streamingId.value = ''
  }

  function fail(message) {
    patchStreamingMessage({ streaming: false, error: message || 'AI 服务繁忙，请稍后重试' })
    streaming.value = false
    streamingId.value = ''
  }

  function reset() {
    sessionId.value = ''
    messages.value = []
    streaming.value = false
    streamingId.value = ''
  }

  return {
    sessionId, messages, streaming, streamingId, lastMessage,
    pushUserMessage, beginBotMessage, appendDelta, setTriageCard, setSources,
    finish, fail, reset, patchStreamingMessage,
  }
})
