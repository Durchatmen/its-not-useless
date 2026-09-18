<script setup>
// 排班维护
// 依赖接口：catalog.js listSchedules
// TODO: 待实现；管理端接口尚未定义，见 api/ 顶部说明
</script>

<template>
  <div class="page">
    <div class="page-head">
      <h2>排班维护</h2>
    </div>

    <el-alert
      class="api-warning"
      type="warning"
      :closable="false"
      show-icon
      title="管理端接口尚未在《接口文档》中定义，本页待接口补齐后实现。"
    />

    <el-empty description="排班维护（待实现）" :image-size="90" />
  </div>
</template>

<style scoped lang="less">
.page {
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  padding: 20px;
}

.page-head {
  margin-bottom: 16px;

  h2 {
    font-size: 18px;
  }
}

.api-warning {
  margin-bottom: 16px;
}
</style>
