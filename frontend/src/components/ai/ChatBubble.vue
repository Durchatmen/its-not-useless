<script setup>
import { computed } from 'vue'

import SourceList from './SourceList.vue'
import TriageCard from './TriageCard.vue'

const props = defineProps({
  /** chat store 中的消息对象 */
  message: { type: Object, required: true },
})

const isUser = computed(() => props.message.role === 'user')
</script>

<template>
  <div class="bubble-row" :class="isUser ? 'is-user' : 'is-bot'">
    <div class="avatar">{{ isUser ? '👤' : '🤖' }}</div>

    <div class="bubble-body">
      <!-- 用户消息：语音/图片输入展示转写或占位提示 -->
      <template v-if="isUser">
        <div class="bubble">
          <template v-if="message.textContent">{{ message.textContent }}</template>
          <template v-else-if="message.inputType === 'VOICE'">🎤 语音消息</template>
          <template v-else-if="message.inputType === 'IMAGE'">🖼️ 图片消息</template>
        </div>
      </template>

      <!-- AI 消息 -->
      <template v-else>
        <div class="bubble">
          <p v-if="message.reply" class="reply">{{ message.reply }}</p>
          <span v-if="message.streaming" class="typing" aria-label="正在生成">▍</span>
          <p v-if="message.error" class="error">{{ message.error }}</p>
        </div>

        <el-alert
          v-if="message.riskWarning"
          class="risk"
          type="error"
          :closable="false"
          show-icon
          :title="message.riskWarning"
        />

        <TriageCard :card="message.triageCard" :disabled="message.streaming" />

        <SourceList :sources="message.sources" :disclaimer="message.disclaimer" />

        <p v-if="message.nextQuestion" class="next-question">{{ message.nextQuestion }}</p>
      </template>
    </div>
  </div>
</template>

<style scoped lang="less">
.bubble-row {
  display: flex;
  gap: 10px;
  margin-bottom: 16px;

  &.is-user {
    flex-direction: row-reverse;

    .bubble {
      background: var(--primary);
      color: #fff;
      border-radius: var(--radius) 0 var(--radius) var(--radius);
    }

    .bubble-body {
      align-items: flex-end;
    }
  }
}

.avatar {
  flex: 0 0 36px;
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: var(--card);
  border: 1px solid var(--line);
  font-size: 18px;
}

.bubble-body {
  display: flex;
  flex-direction: column;
  max-width: 72%;
}

.bubble {
  padding: 10px 14px;
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: 0 var(--radius) var(--radius) var(--radius);
  line-height: 1.7;
  word-break: break-word;
}

.reply {
  white-space: pre-wrap;
}

.typing {
  display: inline-block;
  animation: blink 1s step-end infinite;
}

@keyframes blink {
  50% {
    opacity: 0;
  }
}

.error {
  color: var(--red);
  font-size: 13px;
}

.risk {
  margin-top: 8px;
}

.next-question {
  margin-top: 8px;
  font-size: 13px;
  color: var(--text-2);
}

.mq-md({
  .bubble-body { max-width: 86%; }
});
</style>
