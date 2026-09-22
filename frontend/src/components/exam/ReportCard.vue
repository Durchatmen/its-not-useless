<script setup>
/**
 * 报告卡片 —— 检查与报告列表里的一条（ExamListItem）。
 * 纯展示组件，动作都以事件抛给页面，便于列表页统一处理跳转。
 */
import { EXAM_STATUS } from '@/constants/enums'

defineProps({
  /** ExamListItem */
  exam: { type: Object, required: true },
})
const emit = defineEmits(['view', 'guide', 'queue'])

/** 检查状态 → el-tag 类型与进度色 */
const TAG_TYPE = {
  WAIT_PAY: 'danger',
  WAIT_EXAM: 'warning',
  WAIT_REPORT: 'primary',
  REPORTED: 'success',
}

const hasReport = (exam) => Boolean(exam.reportId) && exam.examStatus === EXAM_STATUS.REPORTED
</script>

<template>
  <div class="report-card">
    <div class="head">
      <h3>{{ exam.examName }}</h3>
      <el-tag size="small" :type="TAG_TYPE[exam.examStatus] || 'info'">
        {{ exam.statusDesc }}
      </el-tag>
    </div>

    <div class="rows">
      <div class="row"><span>就诊人</span><strong>{{ exam.patientName }}</strong></div>
      <div class="row"><span>执行科室</span><strong>{{ exam.deptName }}</strong></div>
      <div class="row">
        <span>检查地点</span>
        <strong>{{ exam.locationText || [exam.building, exam.floor, exam.room].filter(Boolean).join('') || '—' }}</strong>
      </div>
      <div class="row"><span>检查日期</span><strong>{{ exam.examDate || '—' }}</strong></div>
      <div v-if="exam.queueNo" class="row"><span>排队号</span><strong class="queue">{{ exam.queueNo }}</strong></div>
    </div>

    <div class="actions">
      <el-button size="small" @click="emit('guide', exam)">检查指引</el-button>
      <el-button size="small" @click="emit('queue', exam)">排队进度</el-button>
      <el-button v-if="hasReport(exam)" size="small" type="primary" @click="emit('view', exam)">
        查看报告
      </el-button>
      <el-tag v-else size="small" type="info" effect="plain">报告未出</el-tag>
    </div>
  </div>
</template>

<style scoped lang="less">
.report-card {
  padding: 16px;
  .card();
}

.head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;

  h3 {
    font-size: 16px;
    font-weight: 600;
  }
}

.rows {
  margin-top: 12px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.row {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  font-size: 13px;

  span {
    flex: 0 0 auto;
    color: var(--text-2);
  }

  strong {
    font-weight: 500;
    text-align: right;
    .ellipsis();
  }

  .queue {
    color: var(--primary);
  }
}

.actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  margin-top: 14px;
  padding-top: 12px;
  border-top: 1px solid var(--line);
}
</style>
