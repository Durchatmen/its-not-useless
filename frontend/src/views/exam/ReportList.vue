<script setup>
/**
 * 检查报告列表（检查模块入口）。
 *
 * 数据来自 GET /exams（检查列表，按日期倒序）；卡片上的三个动作分别去
 * 检查指引 / 排队进度 / 报告详情，都是本模块内的页面。
 */
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import * as examApi from '@/api/exams'
import EmptyState from '@/components/common/EmptyState.vue'
import PageHeader from '@/components/common/PageHeader.vue'
import ReportCard from '@/components/exam/ReportCard.vue'
import { EXAM_STATUS, EXAM_STATUS_LABEL } from '@/constants/enums'

const router = useRouter()

const STATUS_TABS = [
  { value: '', label: '全部' },
  { value: EXAM_STATUS.WAIT_PAY, label: EXAM_STATUS_LABEL.WAIT_PAY },
  { value: EXAM_STATUS.WAIT_EXAM, label: EXAM_STATUS_LABEL.WAIT_EXAM },
  { value: EXAM_STATUS.WAIT_REPORT, label: EXAM_STATUS_LABEL.WAIT_REPORT },
  { value: EXAM_STATUS.REPORTED, label: EXAM_STATUS_LABEL.REPORTED },
]

const loading = ref(false)
const list = ref([])
const total = ref(0)
const pageNum = ref(1)
const pageSize = ref(10)
const status = ref('')

async function load() {
  loading.value = true
  try {
    const data = await examApi.listExams({
      examStatus: status.value || undefined,
      pageNum: pageNum.value,
      pageSize: pageSize.value,
    })
    list.value = data?.list || []
    total.value = data?.total || 0
  } finally {
    loading.value = false
  }
}

function changeStatus(value) {
  status.value = value
  pageNum.value = 1
  load()
}

const goDetail = (exam) => router.push({ name: 'ReportDetail', params: { examId: exam.examId } })
const goGuide = (exam) =>
  router.push({ name: 'ExamGuide', query: { examId: exam.examId, examName: exam.examName } })
const goQueue = (exam) =>
  router.push({ name: 'ExamQueue', query: { examId: exam.examId, examName: exam.examName } })

onMounted(load)
</script>

<template>
  <div class="page">
    <PageHeader title="检查报告" subtitle="查看检查进度、注意事项与报告解读">
      <template #extra>
        <el-button text type="primary" @click="router.push({ name: 'Home' })">返回首页</el-button>
      </template>
    </PageHeader>

    <div class="panel">
      <div class="tabs">
        <el-button
          v-for="tab in STATUS_TABS"
          :key="tab.value"
          size="small"
          :type="status === tab.value ? 'primary' : 'default'"
          @click="changeStatus(tab.value)"
        >
          {{ tab.label }}
        </el-button>
      </div>

      <div v-loading="loading" class="grid">
        <EmptyState v-if="!loading && !list.length" description="暂无检查记录" />

        <ReportCard
          v-for="exam in list"
          :key="exam.examId"
          :exam="exam"
          @view="goDetail"
          @guide="goGuide"
          @queue="goQueue"
        />
      </div>

      <div v-if="total > pageSize" class="pager">
        <el-pagination
          v-model:current-page="pageNum"
          :page-size="pageSize"
          :total="total"
          layout="prev, pager, next, total"
          @current-change="load"
        />
      </div>
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

.tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding-bottom: 16px;
  margin-bottom: 16px;
  border-bottom: 1px solid var(--line);
}

.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 16px;
  min-height: 120px;
}

.pager {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}

.mq-md({
  .grid { grid-template-columns: 1fr; }
});
</style>
