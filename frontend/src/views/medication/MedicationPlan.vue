<script setup>
/**
 * 用药计划。
 *
 * API-30 取当前处方（含药品明细与禁忌），点「生成用药提醒」调 API-31
 * 按频次算出每天的服药时间点（幂等，重复调用会重建提醒）。
 *
 * 「导出到日历」用本地 ics 生成 .ics 文件下载，不依赖后端：
 * 服务端下发的 calendarExportUrl 指向的日历接口并未挂在路由上（见
 * app/api/v1/medication_reminders.py 的说明），因此这里走前端生成。
 */
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import * as prescriptionApi from '@/api/prescriptions'
import EmptyState from '@/components/common/EmptyState.vue'
import PageHeader from '@/components/common/PageHeader.vue'
import MedicationPlanCard from '@/components/medication/MedicationPlanCard.vue'
import { useIcs } from '@/composables/useIcs'

const router = useRouter()
const { exportReminders } = useIcs()

const loading = ref(false)
const prescription = ref(null)

const generating = ref(false)
const plan = ref(null)

/** 同一种药在一天里有多个时间点，按药名归并后渲染 */
const planGroups = computed(() => {
  const map = new Map()
  for (const item of plan.value?.planItems || []) {
    if (!map.has(item.drugName)) {
      map.set(item.drugName, { drugName: item.drugName, dose: item.dose, times: [], remark: item.remark, mealRelation: item.mealRelation })
    }
    const group = map.get(item.drugName)
    group.times.push(item.time)
    if (!group.mealRelation || group.mealRelation === '不限') group.mealRelation = item.mealRelation
  }
  return [...map.values()].map((group) => ({ ...group, times: [...new Set(group.times)].sort() }))
})

async function load() {
  loading.value = true
  try {
    prescription.value = await prescriptionApi.getCurrentPrescription({})
  } finally {
    loading.value = false
  }
}

async function generate() {
  generating.value = true
  try {
    plan.value = await prescriptionApi.createMedicationReminder({
      prescriptionId: prescription.value.prescriptionId,
      // 方案默认从当天开始，与后端默认行为一致
      startDate: new Date().toISOString().slice(0, 10),
    })
    ElMessage.success('已生成用药提醒')
  } finally {
    generating.value = false
  }
}

async function exportToCalendar() {
  const today = new Date().toISOString().slice(0, 10)
  const reminders = (plan.value?.planItems || []).map((item) => ({
    title: `${item.drugName} ${item.dose || ''}`.trim(),
    date: today,
    time: item.time,
    description: `${item.remark || ''}${item.mealRelation && item.mealRelation !== '不限' ? `（${item.mealRelation}）` : ''}`,
  }))

  if (!reminders.length) {
    ElMessage.warning('请先生成用药提醒')
    return
  }

  try {
    await exportReminders(reminders, `用药提醒-${prescription.value.prescriptionId}.ics`)
    ElMessage.success('已导出日历文件')
  } catch (err) {
    ElMessage.error(`日历导出失败：${err?.message || err}`)
  }
}

onMounted(load)
</script>

<template>
  <div class="page">
    <PageHeader title="用药计划" subtitle="按处方生成服药提醒，可导出到手机日历">
      <template #extra>
        <el-button text type="primary" @click="router.push({ name: 'ReminderSetting' })">
          提醒设置
        </el-button>
      </template>
    </PageHeader>

    <div v-loading="loading" class="body">
      <EmptyState v-if="!loading && !prescription" description="暂无有效处方">
        <el-button type="primary" @click="router.push({ name: 'RecordList' })">查看电子病历</el-button>
      </EmptyState>

      <MedicationPlanCard
        v-else-if="prescription"
        :prescription="prescription"
        @generate="generate"
        @wiki="router.push({ name: 'DrugWiki' })"
      />

      <div v-if="generating" class="panel loading-panel">正在生成服药计划…</div>

      <div v-else-if="plan" class="panel">
        <div class="plan-head">
          <h3>服药提醒计划</h3>
          <span class="meta">共 {{ plan.rowCount }} 条提醒 · 计划编号 {{ plan.reminderId }}</span>
        </div>

        <el-alert
          v-if="plan.conflictWarning"
          type="warning"
          :closable="false"
          show-icon
          :title="plan.conflictWarning"
          class="alert"
        />

        <el-alert
          v-if="plan.unresolved?.length"
          type="info"
          :closable="false"
          show-icon
          :title="`以下药品的用药频次未能识别，已按默认时间安排，请自行核对：${plan.unresolved.join('、')}`"
          class="alert"
        />

        <div class="groups">
          <div v-for="group in planGroups" :key="group.drugName" class="group">
            <div class="group-head">
              <strong>{{ group.drugName }}</strong>
              <span class="dose">{{ group.dose }}</span>
              <el-tag v-if="group.mealRelation" size="small" type="info">{{ group.mealRelation }}</el-tag>
            </div>

            <div class="times">
              <el-tag v-for="time in group.times" :key="time" size="small" type="primary" effect="plain">
                {{ time }}
              </el-tag>
            </div>

            <p class="remark">{{ group.remark }}</p>
          </div>
        </div>

        <p class="disclaimer">{{ plan.disclaimer }}</p>

        <div class="actions">
          <el-button type="primary" @click="exportToCalendar">导出到日历</el-button>
          <el-button @click="router.push({ name: 'ReminderSetting' })">调整提醒时间</el-button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped lang="less">
.page {
  .page-container();
}

.body {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.panel {
  padding: 20px;
  .card();
}

.loading-panel {
  text-align: center;
  color: var(--text-2);
}

.plan-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  padding-bottom: 14px;
  border-bottom: 1px solid var(--line);

  h3 {
    font-size: 15px;
    font-weight: 600;
  }

  .meta {
    font-size: 12px;
    color: var(--text-3);
  }
}

.alert {
  margin-top: 14px;
}

.groups {
  display: flex;
  flex-direction: column;
  gap: 14px;
  margin-top: 16px;
}

.group {
  padding: 14px 16px;
  border: 1px solid var(--line);
  border-radius: var(--radius);
}

.group-head {
  display: flex;
  align-items: center;
  gap: 8px;

  strong {
    font-size: 15px;
  }

  .dose {
    font-size: 13px;
    color: var(--text-2);
  }
}

.times {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 10px;
}

.remark {
  margin-top: 10px;
  font-size: 13px;
  line-height: 1.7;
  color: var(--text-2);
}

.disclaimer {
  margin-top: 18px;
  padding: 10px 12px;
  font-size: 12px;
  color: var(--text-2);
  background: var(--bg);
  border-radius: var(--radius);
}

.actions {
  display: flex;
  gap: 12px;
  margin-top: 16px;
}
</style>
