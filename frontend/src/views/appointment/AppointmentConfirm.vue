<script setup>
/**
 * 确认挂号（挂号第三步）。
 *
 * 号源信息由上一步（选择医生）通过 query 带过来，本页只补「给谁挂 + 备注」，
 * 提交调用 API-11 预约挂号；成功后本地展示结果（挂号单号、队列号、就诊地点）
 * 并给出「去缴费」入口 —— 挂号会同时生成一张挂号费账单（响应里的 billId）。
 */
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import * as appointmentApi from '@/api/appointments'
import EmptyState from '@/components/common/EmptyState.vue'
import PageHeader from '@/components/common/PageHeader.vue'
import { usePatientStore } from '@/stores/patient'
import { formatMoneyText } from '@/utils/format'

const route = useRoute()
const router = useRouter()
const patientStore = usePatientStore()

const scheduleId = String(route.query.scheduleId || '')
const slot = {
  deptName: String(route.query.deptName || ''),
  doctorName: String(route.query.doctorName || ''),
  doctorTitle: String(route.query.doctorTitle || ''),
  specialty: String(route.query.specialty || ''),
  apptDate: String(route.query.apptDate || ''),
  timeSlot: String(route.query.timeSlot || ''),
  fee: Number(route.query.fee || 0),
}

const patientId = ref('')
const source = ref('MANUAL')
const remark = ref('')
const submitting = ref(false)
/** 挂号成功后的响应，非空即切到结果视图 */
const created = ref(null)

const currentPatient = computed(
  () => patientStore.patients.find((item) => item.patientId === patientId.value) || null,
)

async function load() {
  if (!patientStore.patients.length) await patientStore.fetchPatients()
  patientId.value = patientStore.currentPatientId || patientStore.selfPatient?.patientId || ''
}

async function submit() {
  if (!patientId.value) {
    ElMessage.warning('请选择就诊人')
    return
  }

  submitting.value = true
  try {
    created.value = await appointmentApi.createAppointment({
      patientId: patientId.value,
      scheduleId,
      source: source.value,
      remark: remark.value.trim() || undefined,
    })
    // 号源已被占掉，回列表页时必须是新数据
    ElMessage.success('挂号成功')
  } finally {
    submitting.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="page">
    <PageHeader title="确认挂号" subtitle="请核对号源信息与就诊人，确认后生成挂号单" />

    <!-- 缺少号源参数（如手动改 URL）时给出去处，避免页面空转 -->
    <div v-if="!scheduleId" class="panel">
      <EmptyState description="未选择号源时段">
        <el-button type="primary" @click="router.push({ name: 'DeptSelect' })">去选择科室</el-button>
      </EmptyState>
    </div>

    <!-- 挂号成功结果 -->
    <div v-else-if="created" class="panel result">
      <el-result icon="success" title="挂号成功" :sub-title="`挂号单号 ${created.appointmentId}`">
        <template #extra>
          <div class="result-rows">
            <div class="row"><span>就诊人</span><strong>{{ currentPatient?.name }}</strong></div>
            <div class="row"><span>科室</span><strong>{{ created.deptName }}</strong></div>
            <div class="row"><span>医生</span><strong>{{ created.doctorName }}</strong></div>
            <div class="row">
              <span>就诊时间</span>
              <strong>{{ created.apptDate }} {{ created.timeSlot }}</strong>
            </div>
            <div class="row">
              <span>队列号</span>
              <strong class="queue">{{ created.queueNo }}</strong>
            </div>
            <div class="row"><span>就诊地点</span><strong>{{ created.location || '—' }}</strong></div>
            <div class="row"><span>挂号费</span><strong>{{ formatMoneyText(slot.fee) }}</strong></div>
          </div>

          <div class="actions">
            <el-button type="primary" @click="router.push({ name: 'BillList' })">去缴费</el-button>
            <el-button @click="router.push({ name: 'MyAppointments' })">我的挂号</el-button>
          </div>
        </template>
      </el-result>
    </div>

    <!-- 确认表单 -->
    <div v-else class="panel">
      <div class="slot-card">
        <div class="slot-main">
          <h3>{{ slot.deptName }} · {{ slot.doctorName }}</h3>
          <p class="title-line">{{ slot.doctorTitle }}</p>
          <p v-if="slot.specialty" class="specialty">擅长：{{ slot.specialty }}</p>
        </div>
        <div class="slot-side">
          <div class="date">{{ slot.apptDate }}</div>
          <div class="time">{{ slot.timeSlot }}</div>
          <div class="fee">{{ formatMoneyText(slot.fee) }}</div>
        </div>
      </div>

      <el-form label-width="88px" class="form">
        <el-form-item label="就诊人">
          <el-radio-group v-model="patientId">
            <el-radio v-for="item in patientStore.patients" :key="item.patientId" :value="item.patientId">
              {{ item.name }}（{{ item.relationDesc }}）
            </el-radio>
          </el-radio-group>
          <div v-if="!patientStore.patients.length" class="hint">
            暂无就诊人，
            <el-link type="primary" @click="router.push({ name: 'PatientManage' })">去添加</el-link>
          </div>
        </el-form-item>

        <el-form-item label="挂号来源">
          <el-radio-group v-model="source">
            <el-radio value="MANUAL">手动挂号</el-radio>
            <el-radio value="AI_AUTO">AI 自动挂号</el-radio>
          </el-radio-group>
        </el-form-item>

        <el-form-item label="备注">
          <el-input
            v-model="remark"
            type="textarea"
            :rows="3"
            maxlength="255"
            show-word-limit
            placeholder="如：发热三天，需开退烧药（选填，会同步给医生）"
          />
        </el-form-item>
      </el-form>

      <div class="submit-bar">
        <el-button @click="router.back()">返回上一步</el-button>
        <el-button type="primary" :loading="submitting" @click="submit">确认挂号</el-button>
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

.slot-card {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 16px;
  background: var(--primary-light);
  border-radius: var(--radius);

  h3 {
    font-size: 16px;
    font-weight: 600;
  }

  .title-line {
    margin-top: 6px;
    font-size: 13px;
    color: var(--text-2);
  }

  .specialty {
    margin-top: 6px;
    font-size: 13px;
    color: var(--text-2);
    .ellipsis-multi(2);
  }
}

.slot-side {
  flex: 0 0 auto;
  text-align: right;

  .date {
    font-size: 13px;
    color: var(--text-2);
  }

  .time {
    margin-top: 4px;
    font-size: 16px;
    font-weight: 600;
    color: var(--primary);
  }

  .fee {
    margin-top: 4px;
    font-size: 14px;
    color: var(--red);
  }
}

.form {
  margin-top: 20px;
}

.hint {
  font-size: 13px;
  color: var(--text-2);
}

.submit-bar {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding-top: 16px;
  border-top: 1px solid var(--line);
}

.result-rows {
  display: inline-flex;
  flex-direction: column;
  gap: 10px;
  min-width: 300px;
  text-align: left;

  .row {
    display: flex;
    justify-content: space-between;
    gap: 24px;
    font-size: 14px;

    span {
      color: var(--text-2);
    }
  }

  .queue {
    color: var(--primary);
  }
}

.actions {
  display: flex;
  justify-content: center;
  gap: 12px;
  margin-top: 20px;
}

.mq-md({
  .slot-card { flex-direction: column; }
  .slot-side { text-align: left; }
});
</style>
