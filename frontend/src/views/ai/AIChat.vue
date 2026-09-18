<script setup>
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'

import ChatBubble from '@/components/ai/ChatBubble.vue'
import ChatInput from '@/components/ai/ChatInput.vue'
import { useSse } from '@/composables/useSse'
import { useChatStore } from '@/stores/chat'
import { usePatientStore } from '@/stores/patient'
import { AI_INPUT_TYPE } from '@/constants/enums'

const route = useRoute()
const chatStore = useChatStore()
const patientStore = usePatientStore()
const { send, abort } = useSse()

const bodyRef = ref(null)

const quickQuestions = [
  '头痛伴有恶心，需要挂哪个科？',
  '检查报告里的"双肺纹理增粗"是什么意思？',
  '高血压患者在饮食上要注意什么？',
  '这个药可以和降压药一起吃吗？',
]

async function scrollToBottom() {
  await nextTick()
  const el = bodyRef.value
  if (el) el.scrollTop = el.scrollHeight
}

async function handleSend(payload) {
  try {
    await send({
      ...payload,
      patientId: patientStore.currentPatient?.patientId,
    })
  } catch {
    ElMessage.error('AI 服务繁忙，请稍后重试')
  }
}

function handleQuickQuestion(question) {
  handleSend({ inputType: AI_INPUT_TYPE.TEXT, textContent: question })
}

watch(() => chatStore.messages.length, scrollToBottom)
watch(() => chatStore.messages[chatStore.messages.length - 1]?.reply, scrollToBottom)

onMounted(() => {
  // 从预诊页带症状跳转过来时自动发起提问
  const symptom = route.query.symptom
  if (symptom && !chatStore.messages.length) {
    handleSend({ inputType: AI_INPUT_TYPE.TEXT, textContent: String(symptom) })
  }
})

onBeforeUnmount(abort)
</script>

<template>
  <div class="chat-page">
    <header class="chat-head">
      <div class="head-main">
        <h3>AI 陪诊小助手</h3>
        <small>基于 RAG 六大知识库 · 回答标注来源 · 支持文本 / 语音输入</small>
      </div>
      <el-button v-if="chatStore.messages.length" text @click="chatStore.reset()">清空会话</el-button>
    </header>

    <div ref="bodyRef" class="chat-body">
      <!-- 首屏引导 -->
      <div v-if="!chatStore.messages.length" class="chat-intro">
        <span class="intro-icon">🤖</span>
        <h4>您好，我是 AI 陪诊小助手</h4>
        <p>可以描述症状帮您预诊分诊，也可以问我报告、用药、医保的问题。</p>

        <div class="quick-qs">
          <el-button
            v-for="item in quickQuestions"
            :key="item"
            round
            size="small"
            @click="handleQuickQuestion(item)"
          >
            {{ item }}
          </el-button>
        </div>

        <el-alert
          class="intro-alert"
          type="warning"
          :closable="false"
          show-icon
          title="急危重症请直接拨打 120 或前往急诊科。AI 建议不构成医疗诊断。"
        />
      </div>

      <ChatBubble v-for="message in chatStore.messages" :key="message.id" :message="message" />
    </div>

    <ChatInput :disabled="chatStore.streaming" @send="handleSend" @stop="abort" />
  </div>
</template>

<style scoped lang="less">
.chat-page {
  height: calc(100vh - 60px);
  display: flex;
  flex-direction: column;
  background: var(--bg);
}

.chat-head {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 20px;
  background: var(--card);
  border-bottom: 1px solid var(--line);

  h3 {
    font-size: 16px;
  }

  small {
    color: var(--text-3);
    font-size: 12px;
  }
}

.head-main {
  flex: 1;
}

.chat-body {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
  .page-container();
}

.chat-intro {
  text-align: center;
  padding: 40px 16px;

  .intro-icon {
    font-size: 56px;
  }

  h4 {
    margin: 12px 0 8px;
    font-size: 18px;
  }

  p {
    color: var(--text-2);
  }
}

.quick-qs {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 8px;
  margin: 24px 0;
}

.intro-alert {
  max-width: 520px;
  margin: 0 auto;
  text-align: left;
}

.mq-md({
  .chat-page { height: auto; min-height: calc(100vh - 60px); }
});
</style>
