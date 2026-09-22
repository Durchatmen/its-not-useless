<script setup>
/**
 * 科室选择器 —— 数据来自 API-10 查询排班与号源（GET /schedules）。
 *
 * 后端没有独立的「科室列表」接口，科室是从排班结果里按 deptCode 聚合出来的；
 * 因此**只展示当前有排班的科室**，与实际能挂上号的科室天然一致。
 */
import { computed, onMounted, ref, watch } from 'vue'

import * as appointmentApi from '@/api/appointments'
import EmptyState from '@/components/common/EmptyState.vue'
import { formatMoneyText } from '@/utils/format'

const props = defineProps({
  /** 当前选中的科室ID，用于高亮 */
  modelValue: { type: String, default: '' },
  /** 就诊日期 yyyy-MM-dd；留空由后端按当天起 7 天窗口返回 */
  date: { type: String, default: '' },
})
const emit = defineEmits(['update:modelValue', 'select', 'loaded'])

const loading = ref(false)
const schedules = ref([])

/** 按科室聚合：出诊医生数、可约日期、最低挂号费、剩余号源 */
const departments = computed(() => {
  const map = new Map()
  for (const item of schedules.value) {
    if (!map.has(item.deptCode)) {
      map.set(item.deptCode, {
        deptId: item.deptCode,
        deptName: item.deptName,
        doctors: new Set(),
        dates: new Set(),
        minFee: item.fee,
        remaining: 0,
      })
    }
    const dept = map.get(item.deptCode)
    dept.doctors.add(item.doctorId)
    dept.dates.add(item.apptDate)
    dept.remaining += item.remaining || 0
    if (Number(item.fee) < Number(dept.minFee)) dept.minFee = item.fee
  }
  return [...map.values()].map((dept) => ({
    deptId: dept.deptId,
    deptName: dept.deptName,
    doctorCount: dept.doctors.size,
    dates: [...dept.dates].sort(),
    minFee: dept.minFee,
    remaining: dept.remaining,
  }))
})

async function load() {
  loading.value = true
  try {
    // date 为空时不要传空串，否则后端会按「date=''」解析失败
    const data = await appointmentApi.listSchedules({
      date: props.date || undefined,
      pageSize: 100,
    })
    schedules.value = data?.list || []
    emit('loaded', departments.value)
  } finally {
    loading.value = false
  }
}

function pick(dept) {
  emit('update:modelValue', dept.deptId)
  emit('select', dept)
}

onMounted(load)
watch(() => props.date, load)
</script>

<template>
  <div v-loading="loading" class="dept-picker">
    <EmptyState v-if="!loading && !departments.length" description="暂无可预约的科室" />

    <div v-else class="grid">
      <div
        v-for="dept in departments"
        :key="dept.deptId"
        class="dept-card"
        :class="{ active: dept.deptId === modelValue }"
        @click="pick(dept)"
      >
        <div class="head">
          <h3>{{ dept.deptName }}</h3>
          <el-tag v-if="dept.deptId === modelValue" type="primary" size="small">已选</el-tag>
        </div>

        <p class="meta">
          {{ dept.doctorCount }} 位医生 · 可约 {{ dept.dates.length }} 天 · 余号 {{ dept.remaining }}
        </p>

        <div class="foot">
          <span class="fee">挂号费 {{ formatMoneyText(dept.minFee) }} 起</span>
          <span class="go">选择医生 →</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped lang="less">
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 16px;
}

.dept-card {
  padding: 16px;
  cursor: pointer;
  transition: all 0.2s;
  .card();

  &:hover {
    border-color: var(--primary);
    transform: translateY(-2px);
  }

  &.active {
    border-color: var(--primary);
    background: var(--primary-light);
  }
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

.meta {
  margin-top: 8px;
  font-size: 13px;
  color: var(--text-2);
}

.foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 14px;
  font-size: 13px;

  .fee {
    color: var(--red);
  }

  .go {
    color: var(--primary);
  }
}

.mq-md({
  .grid { grid-template-columns: 1fr; }
});
</style>
