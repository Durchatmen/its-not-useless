<script setup>
// 无壳布局：登录 / 注册等不需要导航的页面
</script>

<template>
  <div class="blank-layout">
    <router-view />
  </div>
</template>

<style scoped lang="less">
.blank-layout {
  min-height: 100%;
  display: flex;
  flex-direction: column;
  background: linear-gradient(160deg, var(--primary-light) 0%, var(--bg) 45%);
}
</style>
