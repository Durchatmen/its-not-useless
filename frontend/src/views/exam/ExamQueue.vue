<script setup>
/**
 * 排队进度。
 *
 * API-28 给整条检查流程的进度（待缴费→待检查→待报告→已报告），
 * API-25 给现场叫号（我的号/当前号/前方人数/预计等待），
 * 两者都交给 QueueProgress 组件渲染，并在页面里支持手动刷新
 * —— 叫号是现场实时变化的，用户会反复点刷新，因此不做自动轮询，避免无谓请求。
 */
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import * as examApi from '@/api/exams'
import EmptyState from '@/components/common/EmptyState.vue'
import PageHeader from '@/components/common/PageHeader.vue'
import QueueProgress from '@/components/exam/QueueProgress.vue'

const route = useRoute()
const router = useRouter()

const examId = String(route.query.examId || '')
const examName = String(route.query.examName || '')

const loading = ref(false)
const status = ref(null)
const queue = ref(null)
const updatedAt = ref('')

async function load() {
  if (!examId) return
  loading.value = true
  try {
    const [st, q] = await Promise.allSettled([
      examApi.getExamStatus(examId),
      examApi.getExamQueue(examId),
    ])
    if (st.status === 'fulfilled') status.value = st.value
    if (q.status === 'fulfilled') queue.value = q.value
    updatedAt.value = new Date().toLocaleTimeString('zh-CN', { hour12: false })
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="page">
    <PageHeader
      :title="status?.examName || examName || '排队进度'"
      :subtitle="status ? `当前状态：${status.statusDesc}` : '加载中'"
    >
      <template #extra>
        <el-button size="small" :loading="loading" @click="load">刷新</el-button>
        <el-button size="small" text type="primary" @click="router.push({ name: 'ReportList' })">
          返回列表
        </el-button>
      </template>
    </PageHeader>

    <div v-loading="loading" class="panel">
      <EmptyState v-if="!examId" description="未指定检查单">
        <el-button type="primary" @click="router.push({ name: 'ReportList' })">去检查列表</el-button>
      </EmptyState>

      <template v-else>
        <QueueProgress :steps="status?.steps || []" :queue="queue" />

        <div class="foot">
          <span class="time">最近刷新：{{ updatedAt || '—' }}</span>
          <div class="links">
            <el-button text type="primary" @click="router.push({ name: 'ExamGuide', query: { examId, examName } })">
              检查指引
            </el-button>
            <el-button
              v-if="status?.examStatus === 'REPORTED'"
              text
              type="primary"
              @click="router.push({ name: 'ReportDetail', params: { examId }, query: { examName } })"
            >
              查看报告
            </el-button>
          </div>
        </div>
      </template>
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

.foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 18px;
  padding-top: 14px;
  border-top: 1px solid var(--line);

  .time {
    font-size: 12px;
    color: var(--text-3);
  }

  .links {
    display: flex;
    gap: 8px;
  }
}
</style>
