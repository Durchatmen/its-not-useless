<script setup>
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()

// 对齐 PC 端原型底部圆形导航：首页 / AI陪诊小助手 / 我的
const items = [
  { name: 'Home', icon: '🏠', text: '首页' },
  { name: 'AiChat', icon: '🤖', text: 'AI陪诊小助手', center: true },
  { name: 'Profile', icon: '👤', text: '我的' },
]

function go(name) {
  if (route.name !== name) router.push({ name })
}
</script>

<template>
  <nav class="bottom-nav">
    <div
      v-for="item in items"
      :key="item.name"
      class="bn-item"
      :class="{ active: route.name === item.name, 'bn-center': item.center }"
      @click="go(item.name)"
    >
      <div class="bn-circle">{{ item.icon }}</div>
      <span class="bn-text">{{ item.text }}</span>
    </div>
  </nav>
</template>

<style scoped lang="less">
.bottom-nav {
  position: fixed;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 100;
  display: flex;
  justify-content: center;
  gap: 56px;
  padding: 8px 16px calc(8px + env(safe-area-inset-bottom));
  background: var(--card);
  border-top: 1px solid var(--line);
}

.bn-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  cursor: pointer;
  color: var(--text-3);
  transition: color 0.2s;

  &:hover,
  &.active {
    color: var(--primary);
  }
}

.bn-circle {
  width: 44px;
  height: 44px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: var(--bg);
  font-size: 20px;
}

.bn-center .bn-circle {
  width: 52px;
  height: 52px;
  margin-top: -16px;
  background: linear-gradient(135deg, var(--primary), #2ec9b4);
  color: #fff;
  box-shadow: 0 4px 14px rgba(14, 159, 143, 0.35);
}

.bn-text {
  font-size: 12px;
}
</style>
