<script setup>
defineProps({
  description: { type: String, default: '暂无数据' },
})
</script>

<template>
  <div class="empty-state">
    <el-empty :description="description">
      <slot />
    </el-empty>
  </div>
</template>

<style scoped lang="less">
.empty-state {
  padding: 32px 0;
}
</style>
