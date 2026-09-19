<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { useUserStore } from '@/stores/user'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()

const navLinks = computed(() => [
  { name: 'Home', text: '首页' },
  { name: 'AiChat', text: 'AI陪诊小助手' },
  { name: 'Profile', text: '我的' },
])

function go(name) {
  if (route.name !== name) router.push({ name })
}
</script>

<template>
  <header class="navbar">
    <div class="nav-inner">
      <div class="nav-brand" @click="go('Home')">
        <span class="brand-logo">🩺</span>
        <span class="brand-text">智慧医疗AI辅助系统</span>
      </div>

      <nav class="nav-links">
        <a
          v-for="link in navLinks"
          :key="link.name"
          class="nav-link"
          :class="{ active: route.name === link.name }"
          @click="go(link.name)"
        >
          {{ link.text }}
        </a>
      </nav>

      <div class="nav-user">
        <template v-if="userStore.isLogged">
          <span class="user-name">{{ userStore.displayName || '已登录' }}</span>
        </template>
        <el-button v-else type="primary" text @click="go('Login')">登录 / 注册</el-button>
      </div>
    </div>
  </header>
</template>

<style scoped lang="less">
.navbar {
  position: sticky;
  top: 0;
  z-index: 100;
  background: var(--card);
  border-bottom: 1px solid var(--line);
}

.nav-inner {
  .page-container();
  display: flex;
  align-items: center;
  gap: 24px;
  height: 60px;
}

.nav-brand {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  font-weight: 600;
  color: var(--primary);

  .brand-logo {
    font-size: 22px;
  }
}

.nav-links {
  display: flex;
  gap: 8px;
  margin-left: auto;
}

.nav-link {
  padding: 8px 16px;
  border-radius: var(--radius);
  color: var(--text-2);
  cursor: pointer;
  transition: all 0.2s;

  &:hover {
    background: var(--primary-light);
    color: var(--primary);
  }

  &.active {
    background: var(--primary-light);
    color: var(--primary);
    font-weight: 600;
  }
}

.nav-user {
  margin-left: 8px;
  .user-name {
    color: var(--text);
  }
}

.mq-md({
  .brand-text { display: none; }
  .nav-inner { gap: 8px; }
});
</style>
