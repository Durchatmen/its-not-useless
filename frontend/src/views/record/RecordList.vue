<script setup>
/**
 * 电子病历列表（API-22 历史病历查询）。
 *
 * 支持按就诊人过滤（家庭账号一人管全家）与就诊日期区间筛选，
 * 列表项只给摘要，点开进详情页看 AI 通俗解读。
 */
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import * as recordApi from '@/api/medicalRecords'
import EmptyState from '@/components/common/EmptyState.vue'
import PageHeader from '@/components/common/PageHeader.vue'
import { usePatientStore } from '@/stores/patient'

const router = useRouter()
const patientStore = usePatientStore()

const loading = ref(false)
const list = ref([])
const total = ref(0)
const pageNum = ref(1)
const pageSize = ref(10)
const patientId = ref('')
/** el-date-picker 的 daterange 值：['2026-09-01', '2026-09-30'] */
const dateRange = ref([])

async function load() {
  loading.value = true
  try {
    const data = await recordApi.listMedicalRecords({
      patientId: patientId.value || undefined,
      startDate: dateRange.value?.[0] || undefined,
      endDate: dateRange.value?.[1] || undefined,
      pageNum: pageNum.value,
      pageSize: pageSize.value,
    })
    list.value = data?.list || []
    total.value = data?.total || 0
  } finally {
    loading.value = false
  }
}

function resetPageAndLoad() {
  pageNum.value = 1
  load()
}

const goDetail = (record) =>
  router.push({ name: 'RecordDetail', params: { recordId: record.recordId } })

onMounted(async () => {
  if (!patientStore.patients.length) await patientStore.fetchPatients()
  await load()
})
</script>

<template>
  <div class="page">
    <PageHeader title="电子病历" subtitle="查看历次就诊记录，并可用 AI 把专业术语翻译成大白话">
      <template #extra>
        <el-button text type="primary" @click="router.push({ name: 'AiChat' })">问 AI 医生</el-button>
      </template>
    </PageHeader>

    <div class="panel">
      <div class="filters">
        <el-select
          v-model="patientId"
          placeholder="全部就诊人"
          clearable
          style="width: 180px"
          @change="resetPageAndLoad"
        >
          <el-option
            v-for="item in patientStore.patients"
            :key="item.patientId"
            :label="`${item.name}（${item.relationDesc}）`"
            :value="item.patientId"
          />
        </el-select>

        <el-date-picker
          v-model="dateRange"
          type="daterange"
          value-format="YYYY-MM-DD"
          start-placeholder="就诊开始日期"
          end-placeholder="结束日期"
          style="width: 280px"
          @change="resetPageAndLoad"
        />

        <el-button @click="resetPageAndLoad">查询</el-button>
      </div>

      <div v-loading="loading" class="list">
        <EmptyState v-if="!loading && !list.length" description="暂无病历记录" />

        <div v-for="record in list" :key="record.recordId" class="record" @click="goDetail(record)">
          <div class="record-main">
            <div class="line-1">
              <h3>{{ record.diagnosis }}</h3>
              <el-tag size="small" type="info">{{ record.visitDate }}</el-tag>
            </div>

            <div class="line-2">
              <span>{{ record.deptName }}</span>
              <span>接诊医生：{{ record.doctorName }}</span>
              <span>就诊人：{{ record.patientName }}</span>
            </div>

            <p class="brief">处方：{{ record.prescriptionBrief || '—' }}</p>
          </div>

          <div class="record-actions">
            <el-button size="small" type="primary" plain @click.stop="goDetail(record)">
              AI 解读
            </el-button>
          </div>
        </div>
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

.filters {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  padding-bottom: 16px;
  margin-bottom: 16px;
  border-bottom: 1px solid var(--line);
}

.list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-height: 120px;
}

.record {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 14px 16px;
  border: 1px solid var(--line);
  border-radius: var(--radius);
  cursor: pointer;
  transition: all 0.2s;

  &:hover {
    border-color: var(--primary);
  }
}

.record-main {
  flex: 1;
  min-width: 0;
}

.line-1 {
  display: flex;
  align-items: center;
  gap: 8px;

  h3 {
    font-size: 15px;
    font-weight: 600;
  }
}

.line-2 {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  margin-top: 8px;
  font-size: 13px;
  color: var(--text-2);
}

.brief {
  margin-top: 8px;
  font-size: 13px;
  color: var(--text-3);
  .ellipsis();
}

.record-actions {
  flex: 0 0 auto;
}

.pager {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}

.mq-md({
  .record { flex-direction: column; align-items: stretch; }
  .record-actions { text-align: right; }
});
</style>
