<script setup>
/**
 * 医生卡片 —— 展示一位医生的姓名、职称、擅长方向与可约情况。
 * 纯展示组件，数据由父级从 API-10 的排班结果聚合后传入。
 */
import { formatMoneyText } from '@/utils/format'

defineProps({
  /** 聚合后的医生对象：doctorId/doctorName/doctorTitle/specialty/dates/minFee/remaining */
  doctor: { type: Object, required: true },
  /** 是否为当前选中 */
  active: { type: Boolean, default: false },
})
const emit = defineEmits(['select'])
</script>

<template>
  <div class="doctor-card" :class="{ active }" @click="emit('select', doctor)">
    <div class="avatar">{{ doctor.doctorName?.slice(0, 1) }}</div>

    <div class="body">
      <div class="line-1">
        <h3>{{ doctor.doctorName }}</h3>
        <el-tag size="small" type="info">{{ doctor.doctorTitle }}</el-tag>
      </div>

      <p class="specialty">{{ doctor.specialty || '暂无擅长方向说明' }}</p>

      <div class="line-3">
        <span>可约 {{ doctor.dates.length }} 天</span>
        <span>余号 {{ doctor.remaining }}</span>
        <span class="fee">{{ formatMoneyText(doctor.minFee) }} 起</span>
      </div>
    </div>
  </div>
</template>

<style scoped lang="less">
.doctor-card {
  display: flex;
  gap: 14px;
  padding: 16px;
  cursor: pointer;
  transition: all 0.2s;
  .card();

  &:hover {
    border-color: var(--primary);
  }

  &.active {
    border-color: var(--primary);
    background: var(--primary-light);
  }
}

.avatar {
  flex: 0 0 44px;
  height: 44px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  font-weight: 600;
  color: #fff;
  background: var(--primary);
  border-radius: 50%;
}

.body {
  flex: 1;
  min-width: 0;
}

.line-1 {
  display: flex;
  align-items: center;
  gap: 8px;

  h3 {
    font-size: 16px;
    font-weight: 600;
  }
}

.specialty {
  margin-top: 6px;
  font-size: 13px;
  color: var(--text-2);
  .ellipsis-multi(2);
}

.line-3 {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 10px;
  font-size: 12px;
  color: var(--text-2);

  .fee {
    color: var(--red);
  }
}
</style>
