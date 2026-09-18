<script setup>
import { computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessageBox } from 'element-plus'

import { ADMIN_ROLE_LABEL, MENU, hasRole } from '@/constants/roles'
import { useAdminAppStore } from '@/stores/app'
import { useAdminUserStore } from '@/stores/user'

const route = useRoute()
const router = useRouter()
const appStore = useAdminAppStore()
const userStore = useAdminUserStore()

const menus = computed(() => MENU.filter((item) => hasRole(userStore.role, item.roles)))
const roleText = computed(() => ADMIN_ROLE_LABEL[userStore.role] || userStore.role || '—')

async function handleLogout() {
  await ElMessageBox.confirm('确定要退出登录吗？', '提示', { type: 'warning' })
  await userStore.logout()
  router.push({ name: 'AdminLogin' })
}

onMounted(() => appStore.init())
</script>

<template>
  <el-container class="admin-layout">
    <el-aside :width="appStore.sidebarCollapsed ? '64px' : '220px'" class="aside">
      <div class="brand">
        <span class="logo">🩺</span>
        <span v-if="!appStore.sidebarCollapsed" class="brand-text">管理后台</span>
      </div>

      <el-menu
        :default-active="String(route.name)"
        :collapse="appStore.sidebarCollapsed"
        router
        class="menu"
      >
        <el-menu-item
          v-for="item in menus"
          :key="item.name"
          :index="item.name"
          :route="{ name: item.name }"
        >
          <span class="menu-icon">{{ item.icon }}</span>
          <template #title>{{ item.text }}</template>
        </el-menu-item>
      </el-menu>
    </el-aside>

    <el-container>
      <el-header class="header">
        <el-button text @click="appStore.toggleSidebar()">☰</el-button>

        <el-breadcrumb separator="/">
          <el-breadcrumb-item>管理后台</el-breadcrumb-item>
          <el-breadcrumb-item>{{ route.meta.title }}</el-breadcrumb-item>
        </el-breadcrumb>

        <div class="header-right">
          <el-tooltip content="大字模式">
            <el-button text @click="appStore.toggleLargeFont()">🔍</el-button>
          </el-tooltip>
          <el-tooltip content="高对比度">
            <el-button text @click="appStore.toggleHighContrast()">🌓</el-button>
          </el-tooltip>

          <el-tag size="small" type="info">{{ roleText }}</el-tag>
          <span class="user-name">{{ userStore.displayName || '未命名' }}</span>
          <el-button text @click="handleLogout">退出</el-button>
        </div>
      </el-header>

      <el-main class="main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<style scoped lang="less">
.admin-layout {
  height: 100vh;
}

.aside {
  background: var(--card);
  border-right: 1px solid var(--line);
  transition: width 0.2s;
  overflow-x: hidden;
}

.brand {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  height: 60px;
  color: var(--primary);
  font-weight: 600;

  .logo {
    font-size: 22px;
  }
}

.menu {
  border-right: none;
}

.menu-icon {
  margin-right: 8px;
}

.header {
  display: flex;
  align-items: center;
  gap: 16px;
  background: var(--card);
  border-bottom: 1px solid var(--line);
}

.header-right {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 8px;
}

.user-name {
  font-size: 13px;
  color: var(--text-2);
}

.main {
  background: var(--bg);
  padding: 16px;
}
</style>
