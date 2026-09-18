<script setup>
import { ref } from 'vue'
import { ElMessage } from 'element-plus'

import { useVoice } from '@/composables/useVoice'
import { AI_INPUT_TYPE } from '@/constants/enums'

const props = defineProps({
  disabled: { type: Boolean, default: false },
})

const emit = defineEmits(['send', 'stop'])

const text = ref('')
const { recording, seconds, start, stop, blobToBase64 } = useVoice()

function sendText() {
  const content = text.value.trim()
  if (!content || props.disabled) return
  emit('send', { inputType: AI_INPUT_TYPE.TEXT, textContent: content })
  text.value = ''
}

async function toggleVoice() {
  if (props.disabled) return

  if (recording.value) {
    const blob = await stop()
    if (!blob) return
    const audioData = await blobToBase64(blob)
    emit('send', {
      inputType: AI_INPUT_TYPE.VOICE,
      // 浏览器默认产出 webm/opus，audioFormat 待转码方案确定后调整（方案 §8 待办 2）
      audioFormat: 'webm',
      audioData,
    })
    return
  }

  try {
    await start()
  } catch (error) {
    ElMessage.warning(error.message || '无法启动录音')
  }
}
</script>

<template>
  <div class="chat-input">
    <el-input
      v-model="text"
      type="textarea"
      :rows="2"
      resize="none"
      maxlength="500"
      show-word-limit
      placeholder="描述您的症状，例如：头痛伴有恶心，持续两天"
      :disabled="disabled"
      @keydown.enter.exact.prevent="sendText"
    />

    <div class="actions">
      <el-button
        class="voice-btn"
        :type="recording ? 'danger' : 'default'"
        :disabled="disabled"
        @click="toggleVoice"
      >
        {{ recording ? `停止录音 ${seconds}s` : '🎤 语音输入' }}
      </el-button>

      <el-button v-if="disabled" @click="emit('stop')">停止生成</el-button>
      <el-button v-else type="primary" :disabled="!text.trim()" @click="sendText">
        发送
      </el-button>
    </div>
  </div>
</template>

<style scoped lang="less">
.chat-input {
  padding: 12px 16px calc(12px + env(safe-area-inset-bottom));
  background: var(--card);
  border-top: 1px solid var(--line);
}

.actions {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 8px;
}
</style>
