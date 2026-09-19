<script setup>
import { computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'

import AiFab from '@/components/common/AiFab.vue'
import AppNavbar from '@/components/common/AppNavbar.vue'
import BottomNav from '@/components/common/BottomNav.vue'
import { usePatientStore } from '@/stores/patient'
import { useUserStore } from '@/stores/user'

const route = useRoute()
const userStore = useUserStore()
const patientStore = usePatientStore()

const showBottomNav = computed(() => !route.meta.hideBottomNav)
const isFullscreen = computed(() => Boolean(route.meta.fullscreen))

onMounted(() => {
  // 登录后预取就诊人，供各业务页面直接使用
  if (userStore.isLogged) patientStore.fetchPatients().catch(() => {})
})
</script>

<template>
  <div class="default-layout">
    <AppNavbar />

    <main class="layout-main" :class="{ 'is-fullscreen': isFullscreen }">
      <router-view />
    </main>

    <BottomNav v-if="showBottomNav" />

    <!-- 全局 AI 入口：页面右下角悬浮球（功能设计 5.2） -->
    <AiFab v-if="!isFullscreen" />
  </div>
</template>

<style scoped lang="less">
.default-layout {
  min-height: 100%;
  display: flex;
  flex-direction: column;
}

.layout-main {
  flex: 1;
  padding-bottom: 72px; // 给底部导航让位

  &.is-fullscreen {
    padding-bottom: 0;
  }
}
</style>
