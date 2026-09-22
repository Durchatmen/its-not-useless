<script setup>
/**
 * 提醒设置。
 *
 * 后端没有「读取已有提醒」的接口（api/v1/medication_reminders.py 只挂了 API-31 生成），
 * 所以本页自己调一次 API-31 拿到推荐时间点 —— 该接口是幂等的，重复调用会先清旧再写新，
 * 不会产生重复提醒。用户在本页调整的时间点只作用于「导出到日历」的 .ics 文件。
 */
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import * as prescriptionApi from '@/api/prescriptions'
import EmptyState from '@/components/common/EmptyState.vue'
import PageHeader from '@/components/common/PageHeader.vue'
import ReminderTimePicker from '@/components/medication/ReminderTimePicker.vue'
import { useIcs } from '@/composables/useIcs'

const router = useRouter()
const { exportReminders } = useIcs()

const loading = ref(false)
const plan = ref(null)
/** { 药名: ['08:00', ...] } */
const timesByDrug = ref({})

const drugs = computed(() => {
  const map = new Map()
  for (const item of plan.value?.planItems || []) {
    if (!map.has(item.drugName)) {
      map.set(item.drugName, { drugName: item.drugName, dose: item.dose, mealRelation: item.mealRelation, remark: item.remark, options: [] })
    }
    const drug = map.get(item.drugName)
    if (!drug.options.includes(item.time)) drug.options.push(item.time)
  }
  return [...map.values()].map((drug) => ({ ...drug, options: drug.options.sort() }))
})

async function load() {
  loading.value = true
  try {
    const prescription = await prescriptionApi.getCurrentPrescription({})
    if (!prescription) return

    plan.value = await prescriptionApi.createMedicationReminder({
      prescriptionId: prescription.prescriptionId,
      startDate: new Date().toISOString().slice(0, 10),
    })

    // 默认沿用算法给的时间点
    const next = {}
    for (const drug of drugs.value) next[drug.drugName] = [...drug.options]
    timesByDrug.value = next
  } finally {
    loading.value = false
  }
}

function updateTimes(drugName, times) {
  timesByDrug.value = { ...timesByDrug.value, [drugName]: times }
}

async function exportToCalendar() {
  const today = new Date().toISOString().slice(0, 10)
  const reminders = []

  for (const drug of drugs.value) {
    for (const time of timesByDrug.value[drug.drugName] || []) {
      reminders.push({
        title: `${drug.drugName} ${drug.dose || ''}`.trim(),
        date: today,
        time,
        description: `${drug.remark || ''}${drug.mealRelation && drug.mealRelation !== '不限' ? `（${drug.mealRelation}）` : ''}`,
      })
    }
  }

  if (!reminders.length) {
    ElMessage.warning('请至少为一种药设置提醒时间')
    return
  }

  try {
    await exportReminders(reminders, '用药提醒.ics')
    ElMessage.success(`已导出 ${reminders.length} 条提醒`)
  } catch (err) {
    ElMessage.error(`日历导出失败：${err?.message || err}`)
  }
}

onMounted(load)
</script>

<template>
  <div class="page">
    <PageHeader title="提醒设置" subtitle="调整每种药的服药提醒时间，然后导出到手机日历">
      <template #extra>
        <el-button text type="primary" @click="router.push({ name: 'MedicationPlan' })">
          返回用药计划
        </el-button>
      </template>
    </PageHeader>

    <div v-loading="loading" class="panel">
      <EmptyState v-if="!loading && !drugs.length" description="暂无可设置提醒的药品">
        <el-button type="primary" @click="router.push({ name: 'MedicationPlan' })">去生成用药计划</el-button>
      </EmptyState>

      <template v-else>
        <div v-for="drug in drugs" :key="drug.drugName" class="drug-block">
          <div class="drug-head">
            <strong>{{ drug.drugName }}</strong>
            <span class="dose">{{ drug.dose }}</span>
            <el-tag v-if="drug.mealRelation" size="small" type="info">{{ drug.mealRelation }}</el-tag>
          </div>

          <ReminderTimePicker
            :model-value="timesByDrug[drug.drugName] || []"
            :options="drug.options"
            :hint="drug.remark"
            @update:model-value="updateTimes(drug.drugName, $event)"
          />
        </div>

        <p v-if="plan?.disclaimer" class="disclaimer">{{ plan.disclaimer }}</p>

        <div class="actions">
          <el-button type="primary" @click="exportToCalendar">导出到日历</el-button>
          <el-button @click="load">恢复推荐时间</el-button>
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

.drug-block {
  padding-bottom: 18px;
  margin-bottom: 18px;
  border-bottom: 1px dashed var(--line);

  &:last-of-type {
    border-bottom: none;
  }
}

.drug-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;

  strong {
    font-size: 15px;
  }

  .dose {
    font-size: 13px;
    color: var(--text-2);
  }
}

.disclaimer {
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
