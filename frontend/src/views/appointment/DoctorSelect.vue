<script setup>
/**
 * 选择医生（挂号第二步）。
 *
 * 一次 API-10 拉全科室排班，本地按医生聚合；选中医生后展开他/她的排班表，
 * 点中某个号源时段即带参跳到确认页（第三步不再重复请求排班接口）。
 */
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import * as appointmentApi from '@/api/appointments'
import DoctorCard from '@/components/appointment/DoctorCard.vue'
import ScheduleTable from '@/components/appointment/ScheduleTable.vue'
import EmptyState from '@/components/common/EmptyState.vue'
import PageHeader from '@/components/common/PageHeader.vue'

const route = useRoute()
const router = useRouter()

const deptId = String(route.query.deptId || '')
const deptName = String(route.query.deptName || '科室')

const loading = ref(false)
const schedules = ref([])
const selectedDoctorId = ref('')
const selectedScheduleId = ref('')
const dateFilter = ref('')

/** 有排班的日期，用于顶部快捷筛选 */
const dates = computed(() => [...new Set(schedules.value.map((item) => item.apptDate))].sort())

const visibleSchedules = computed(() =>
  dateFilter.value
    ? schedules.value.filter((item) => item.apptDate === dateFilter.value)
    : schedules.value,
)

/** 按医生聚合出卡片所需的字段 */
const doctors = computed(() => {
  const map = new Map()
  for (const item of visibleSchedules.value) {
    if (!map.has(item.doctorId)) {
      map.set(item.doctorId, {
        doctorId: item.doctorId,
        doctorName: item.doctorName,
        doctorTitle: item.doctorTitle,
        specialty: item.specialty,
        deptName: item.deptName,
        dates: new Set(),
        remaining: 0,
        minFee: item.fee,
      })
    }
    const doctor = map.get(item.doctorId)
    doctor.dates.add(item.apptDate)
    doctor.remaining += item.remaining || 0
    if (Number(item.fee) < Number(doctor.minFee)) doctor.minFee = item.fee
  }
  return [...map.values()].map((doctor) => ({ ...doctor, dates: [...doctor.dates].sort() }))
})

const activeDoctor = computed(
  () => doctors.value.find((doctor) => doctor.doctorId === selectedDoctorId.value) || null,
)

/** 选中医生名下的号源，交给 ScheduleTable 按日期分行渲染 */
const activeDoctorSchedules = computed(() =>
  visibleSchedules.value.filter((item) => item.doctorId === selectedDoctorId.value),
)

async function load() {
  loading.value = true
  try {
    const data = await appointmentApi.listSchedules({ deptId, pageSize: 100 })
    schedules.value = data?.list || []
    // 默认展开第一位医生，少一次点击
    if (doctors.value.length) selectedDoctorId.value = doctors.value[0].doctorId
  } finally {
    loading.value = false
  }
}

function toggleDate(date) {
  dateFilter.value = dateFilter.value === date ? '' : date
  // 日期切换后原先选中的医生可能当天不出诊，回落到第一位
  if (!doctors.value.some((doctor) => doctor.doctorId === selectedDoctorId.value)) {
    selectedDoctorId.value = doctors.value[0]?.doctorId || ''
  }
}

function handleSlotSelect(slot) {
  router.push({
    name: 'AppointmentConfirm',
    query: {
      scheduleId: slot.scheduleId,
      deptName: slot.deptName,
      doctorId: slot.doctorId,
      doctorName: slot.doctorName,
      doctorTitle: slot.doctorTitle,
      specialty: slot.specialty || '',
      apptDate: slot.apptDate,
      timeSlot: slot.timeSlot,
      fee: String(slot.fee),
    },
  })
}

onMounted(load)
</script>

<template>
  <div class="page">
    <PageHeader :title="`选择医生 · ${deptName}`" subtitle="选中医生后点击号源时段进入确认页">
      <template #extra>
        <el-button text type="primary" @click="router.push({ name: 'DeptSelect' })">
          重选科室
        </el-button>
      </template>
    </PageHeader>

    <div v-loading="loading" class="panel">
      <div class="date-bar">
        <span class="label">就诊日期</span>
        <el-button :type="dateFilter ? 'default' : 'primary'" size="small" @click="dateFilter = ''">
          全部
        </el-button>
        <el-button
          v-for="date in dates"
          :key="date"
          :type="dateFilter === date ? 'primary' : 'default'"
          size="small"
          @click="toggleDate(date)"
        >
          {{ date.slice(5) }}
        </el-button>
      </div>

      <EmptyState v-if="!loading && !doctors.length" description="该科室暂无可用号源" />

      <template v-else>
        <div class="doctor-grid">
          <DoctorCard
            v-for="doctor in doctors"
            :key="doctor.doctorId"
            :doctor="doctor"
            :active="doctor.doctorId === selectedDoctorId"
            @select="selectedDoctorId = $event.doctorId"
          />
        </div>

        <div v-if="activeDoctor" class="schedule-block">
          <h3 class="block-title">
            {{ activeDoctor.doctorName }} · {{ activeDoctor.doctorTitle }}
            <small>可选号源</small>
          </h3>
          <ScheduleTable
            v-model="selectedScheduleId"
            :schedules="activeDoctorSchedules"
            @select="handleSlotSelect"
          />
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

.date-bar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  padding-bottom: 16px;
  margin-bottom: 16px;
  border-bottom: 1px solid var(--line);

  .label {
    font-size: 13px;
    color: var(--text-2);
  }
}

.doctor-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 16px;
}

.schedule-block {
  margin-top: 24px;
  padding-top: 20px;
  border-top: 1px solid var(--line);
}

.block-title {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin-bottom: 14px;
  font-size: 15px;
  font-weight: 600;

  small {
    font-size: 12px;
    font-weight: 400;
    color: var(--text-3);
  }
}

.mq-md({
  .doctor-grid { grid-template-columns: 1fr; }
});
</style>
