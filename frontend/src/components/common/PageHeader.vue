<script setup>
import { useRouter } from 'vue-router'

defineProps({
  title: { type: String, default: '' },
  subtitle: { type: String, default: '' },
  /** 是否显示返回按钮 */
  back: { type: Boolean, default: true },
})

const router = useRouter()

function goBack() {
  if (window.history.length > 1) router.back()
  else router.push({ name: 'Home' })
}
</script>

<template>
  <div class="page-header">
    <el-button v-if="back" text class="back-btn" @click="goBack">← 返回</el-button>

    <div class="titles">
      <h2>{{ title }}</h2>
      <p v-if="subtitle">{{ subtitle }}</p>
    </div>

    <div class="extra">
      <slot name="extra" />
    </div>
  </div>
</template>

<style scoped lang="less">
.page-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px 0;
}

.back-btn {
  flex: 0 0 auto;
}

.titles {
  flex: 1;
  min-width: 0;

  h2 {
    font-size: 20px;
    font-weight: 600;
  }

  p {
    margin-top: 4px;
    font-size: 13px;
    color: var(--text-2);
  }
}

.extra {
  flex: 0 0 auto;
}
</style>
