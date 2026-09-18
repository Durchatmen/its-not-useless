<script setup>
import { useRoute, useRouter } from 'vue-router'

// 全局 AI 助手入口悬浮球（功能设计 5.2）
const route = useRoute()
const router = useRouter()

function open() {
  if (route.name !== 'AiChat') router.push({ name: 'AiChat' })
}
</script>

<template>
  <button class="ai-fab" type="button" aria-label="打开 AI 陪诊小助手" @click="open">
    <span class="fab-icon">🤖</span>
    <span class="fab-text">AI 助手</span>
  </button>
</template>

<style scoped lang="less">
.ai-fab {
  position: fixed;
  right: 24px;
  bottom: 96px;
  z-index: 99;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 12px 18px;
  border: none;
  border-radius: 999px;
  background: linear-gradient(135deg, var(--primary), #2ec9b4);
  color: #fff;
  font-size: 14px;
  cursor: pointer;
  box-shadow: 0 6px 20px rgba(14, 159, 143, 0.4);
  transition: transform 0.2s;

  &:hover {
    transform: translateY(-2px);
  }
}

.fab-icon {
  font-size: 18px;
}

.mq-md({
  .fab-text { display: none; }
  .ai-fab { padding: 14px; right: 16px; bottom: 88px; }
});
</style>
