<script setup>
/**
 * 选择科室（挂号第一步）。
 *
 * 挂号主链路：选择科室 → 选择医生 → 确认挂号 → 我的挂号
 * 上游入口：首页 / 分诊结果卡片的「去挂号」按钮（GO_REGISTER）。
 */
import { ref } from 'vue'
import { useRouter } from 'vue-router'

import DeptPicker from '@/components/appointment/DeptPicker.vue'
import PageHeader from '@/components/common/PageHeader.vue'

const router = useRouter()

const selected = ref('')

/** 选中科室后进入第二步；科室ID与名称一并带过去，避免下一页再查一次 */
function handleSelect(dept) {
  router.push({
    name: 'DoctorSelect',
    query: { deptId: dept.deptId, deptName: dept.deptName },
  })
}
</script>

<template>
  <div class="page">
    <PageHeader title="选择科室" subtitle="请选择要就诊的科室，下一步选择医生与号源时段">
      <template #extra>
        <el-button text type="primary" @click="router.push({ name: 'MyAppointments' })">
          我的挂号
        </el-button>
      </template>
    </PageHeader>

    <div class="panel">
      <DeptPicker v-model="selected" @select="handleSelect" />
    </div>
  </div>
</template>

<style scoped lang="less">
.page {
  .page-container();
}

.panel {
  padding: 20px;
  .card();
}
</style>
