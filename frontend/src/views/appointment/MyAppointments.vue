<script setup>
/**
 * 我的挂号（挂号第四步）。
 *
 * 一个页面用到挂号模块的三条接口：
 *   API-14 挂号历史（列表 + 状态筛选 + 分页）
 *   API-15 候诊提醒（对话框里展示队列号与预计叫号时间）
 *   API-13 取消挂号 / API-12 修改挂号（改期）
 *
 * 改期的号源列表由 API-10 现查：挂号历史响应里只有医生姓名没有 doctorId，
 * 因此按「科室名 + 医生名」两个字段回捞该医生的其它可约时段。
 */
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'

import * as appointmentApi from '@/api/appointments'
import EmptyState from '@/components/common/EmptyState.vue'
import PageHeader from '@/components/common/PageHeader.vue'
import { APPOINTMENT_STATUS, APPOINTMENT_STATUS_LABEL, APPOINTMENT_STATUS_TAG } from '@/constants/enums'

const router = useRouter()

const STATUS_TABS = [
  { value: '', label: '全部' },
  { value: APPOINTMENT_STATUS.BOOKED, label: APPOINTMENT_STATUS_LABEL.BOOKED },
  { value: APPOINTMENT_STATUS.CHECKED_IN, label: APPOINTMENT_STATUS_LABEL.CHECKED_IN },
  { value: APPOINTMENT_STATUS.FINISHED, label: APPOINTMENT_STATUS_LABEL.FINISHED },
  { value: APPOINTMENT_STATUS.CANCELED, label: APPOINTMENT_STATUS_LABEL.CANCELED },
]

const loading = ref(false)
const list = ref([])
const total = ref(0)
const pageNum = ref(1)
const pageSize = ref(10)
const status = ref('')

/* ---------------- 列表 ---------------- */
async function load() {
  loading.value = true
  try {
    const data = await appointmentApi.listAppointmentHistory({
      pageNum: pageNum.value,
      pageSize: pageSize.value,
      status: status.value || undefined,
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

/* ---------------- 候诊提醒（API-15）---------------- */
const reminder = ref(null)
const reminderVisible = ref(false)
const reminderTarget = ref(null)

async function openReminder(item) {
  reminderTarget.value = item
  reminder.value = null
  reminderVisible.value = true
  try {
    reminder.value = await appointmentApi.getAppointmentReminder(item.appointmentId)
  } catch {
    reminderVisible.value = false
  }
}

/* ---------------- 取消挂号（API-13）---------------- */
async function cancel(item) {
  try {
    await ElMessageBox.confirm(
      `确认取消 ${item.apptDate} ${item.timeSlot} ${item.doctorName} 的挂号吗？`,
      '取消挂号',
      { type: 'warning', confirmButtonText: '确认取消', cancelButtonText: '再想想' },
    )
  } catch {
    return // 用户点了「再想想」
  }

  await appointmentApi.cancelAppointment(item.appointmentId)
  ElMessage.success('已取消挂号')
  load()
}

/* ---------------- 改期（API-12）---------------- */
const rescheduleVisible = ref(false)
const rescheduleTarget = ref(null)
const rescheduleSlots = ref([])
const rescheduleLoading = ref(false)
const pickedScheduleId = ref('')

async function openReschedule(item) {
  rescheduleTarget.value = item
  rescheduleSlots.value = []
  pickedScheduleId.value = ''
  rescheduleVisible.value = true
  rescheduleLoading.value = true
  try {
    const data = await appointmentApi.listSchedules({ pageSize: 100 })
    rescheduleSlots.value = (data?.list || []).filter(
      (slot) =>
        slot.deptName === item.deptName &&
        slot.doctorName === item.doctorName &&
        // 历史响应里没有 scheduleId，用「日期 + 时段」排除当前这一次
        !(slot.apptDate === item.apptDate && slot.timeSlot === item.timeSlot),
    )
  } finally {
    rescheduleLoading.value = false
  }
}

async function submitReschedule() {
  if (!pickedScheduleId.value) {
    ElMessage.warning('请选择新的号源时段')
    return
  }
  await appointmentApi.updateAppointment(rescheduleTarget.value.appointmentId, {
    scheduleId: pickedScheduleId.value,
  })
  ElMessage.success('改期成功')
  rescheduleVisible.value = false
  load()
}

const canReschedule = (item) => item.appointmentStatus === APPOINTMENT_STATUS.BOOKED
const canCancel = (item) => item.appointmentStatus === APPOINTMENT_STATUS.BOOKED
const canRemind = (item) =>
  [APPOINTMENT_STATUS.BOOKED, APPOINTMENT_STATUS.CHECKED_IN].includes(item.appointmentStatus)

onMounted(load)
</script>

<template>
  <div class="page">
    <PageHeader title="我的挂号" subtitle="查看挂号记录、候诊进度，并支持改期或取消">
      <template #extra>
        <el-button type="primary" @click="router.push({ name: 'DeptSelect' })">去挂号</el-button>
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

      <div v-loading="loading" class="list">
        <EmptyState v-if="!loading && !list.length" description="暂无挂号记录">
          <el-button type="primary" @click="router.push({ name: 'DeptSelect' })">去挂号</el-button>
        </EmptyState>

        <div v-for="item in list" :key="item.appointmentId" class="record">
          <div class="record-main">
            <div class="line-1">
              <h3>{{ item.deptName || '—' }} · {{ item.doctorName || '—' }}</h3>
              <el-tag size="small" :type="APPOINTMENT_STATUS_TAG[item.appointmentStatus]">
                {{ item.statusDesc || APPOINTMENT_STATUS_LABEL[item.appointmentStatus] }}
              </el-tag>
            </div>

            <div class="line-2">
              <span>就诊人：{{ item.patientName }}</span>
              <span>时间：{{ item.apptDate }} {{ item.timeSlot }}</span>
              <span>队列号：{{ item.queueNo || '—' }}</span>
            </div>

            <div class="line-3">
              <span>挂号单号：{{ item.appointmentId }}</span>
              <span>挂号时间：{{ item.createTime }}</span>
            </div>
          </div>

          <div class="record-actions">
            <el-button v-if="canRemind(item)" size="small" @click="openReminder(item)">
              候诊提醒
            </el-button>
            <el-button v-if="canReschedule(item)" size="small" @click="openReschedule(item)">
              改期
            </el-button>
            <el-button v-if="canCancel(item)" size="small" type="danger" plain @click="cancel(item)">
              取消挂号
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

    <!-- 候诊提醒 -->
    <el-dialog v-model="reminderVisible" title="候诊提醒" width="420px">
      <div v-if="!reminder" class="loading-box">加载中…</div>
      <template v-else>
        <div class="reminder-rows">
          <div class="row"><span>当前状态</span><strong>{{ reminder.statusDesc }}</strong></div>
          <div class="row"><span>我的队列号</span><strong class="queue">{{ reminder.queueNo || '—' }}</strong></div>
          <div class="row"><span>当前叫号</span><strong>{{ reminder.currentNo || '—' }}</strong></div>
          <div class="row"><span>前方等待</span><strong>{{ reminder.peopleAhead ?? '—' }} 人</strong></div>
          <div class="row"><span>预计等待</span><strong>{{ reminder.estimatedWaitMinutes ?? '—' }} 分钟</strong></div>
          <div class="row"><span>预计叫号</span><strong>{{ reminder.estimatedTime || '—' }}</strong></div>
        </div>
        <p class="note">{{ reminder.estimateNote }}</p>
      </template>
    </el-dialog>

    <!-- 改期 -->
    <el-dialog v-model="rescheduleVisible" title="改期" width="560px">
      <p class="dialog-tip">
        当前：{{ rescheduleTarget?.apptDate }} {{ rescheduleTarget?.timeSlot }} ·
        {{ rescheduleTarget?.doctorName }}
      </p>

      <div v-loading="rescheduleLoading" class="reschedule-body">
        <EmptyState v-if="!rescheduleLoading && !rescheduleSlots.length" description="该医生暂无可改期的号源" />
        <div v-else class="slot-grid">
          <button
            v-for="slot in rescheduleSlots"
            :key="slot.scheduleId"
            type="button"
            class="slot"
            :class="{ active: pickedScheduleId === slot.scheduleId }"
            @click="pickedScheduleId = slot.scheduleId"
          >
            <span class="date">{{ slot.apptDate.slice(5) }}</span>
            <span class="time">{{ slot.timeSlot }}</span>
            <span class="rest">余 {{ slot.remaining }}</span>
          </button>
        </div>
      </div>

      <template #footer>
        <el-button @click="rescheduleVisible = false">取消</el-button>
        <el-button type="primary" :disabled="!pickedScheduleId" @click="submitReschedule">
          确认改期
        </el-button>
      </template>
    </el-dialog>
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

.line-2,
.line-3 {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  margin-top: 8px;
  font-size: 13px;
  color: var(--text-2);
}

.line-3 {
  font-size: 12px;
  color: var(--text-3);
}

.record-actions {
  flex: 0 0 auto;
  display: flex;
  gap: 8px;
}

.pager {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}

.reminder-rows {
  display: flex;
  flex-direction: column;
  gap: 10px;

  .row {
    display: flex;
    justify-content: space-between;
    font-size: 14px;

    span {
      color: var(--text-2);
    }
  }

  .queue {
    color: var(--primary);
  }
}

.note {
  margin-top: 14px;
  padding: 10px 12px;
  font-size: 12px;
  color: var(--text-2);
  background: var(--bg);
  border-radius: var(--radius);
}

.loading-box {
  padding: 24px 0;
  text-align: center;
  color: var(--text-2);
}

.dialog-tip {
  margin-bottom: 12px;
  font-size: 13px;
  color: var(--text-2);
}

.reschedule-body {
  min-height: 90px;
}

.slot-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  gap: 10px;
}

.slot {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  padding: 8px;
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  cursor: pointer;

  .date,
  .rest {
    font-size: 12px;
    color: var(--text-2);
  }

  .time {
    font-size: 14px;
    font-weight: 600;
  }

  &:hover {
    border-color: var(--primary);
  }

  &.active {
    border-color: var(--primary);
    background: var(--primary-light);
  }
}

.mq-md({
  .record { flex-direction: column; align-items: stretch; }
  .record-actions { justify-content: flex-end; }
});
</style>
