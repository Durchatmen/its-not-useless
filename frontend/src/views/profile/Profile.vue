<script setup>
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'

import EmptyState from '@/components/common/EmptyState.vue'
import { RELATION_LABEL } from '@/constants/enums'
import { usePatientStore } from '@/stores/patient'
import { useUserStore } from '@/stores/user'

const router = useRouter()
const userStore = useUserStore()
const patientStore = usePatientStore()

const entries = [
  { name: 'MyAppointments', icon: '📅', text: '我的挂号', desc: '预约记录与候诊进度' },
  { name: 'ReportList', icon: '🔬', text: '检查报告', desc: '报告查询与 AI 解读' },
  { name: 'RecordList', icon: '📋', text: '电子病历', desc: '诊断结果与处方信息' },
  { name: 'BillList', icon: '💳', text: '我的账单', desc: '费用明细与诊间结算' },
  { name: 'MedicationPlan', icon: '💊', text: '用药计划', desc: '服药提醒与药品百科' },
  { name: 'Settings', icon: '⚙️', text: '设置', desc: '大字模式 / 高对比度 / 通知授权' },
]

function go(name) {
  router.push({ name })
}

async function handleLogout() {
  await ElMessageBox.confirm('确定要退出登录吗？', '提示', { type: 'warning' })
  userStore.logout()
  patientStore.reset()
  ElMessage.success('已退出登录')
  router.push({ name: 'Login' })
}

onMounted(() => {
  if (userStore.isLogged) patientStore.fetchPatients().catch(() => {})
})
</script>

<template>
  <div class="page">
    <!-- 用户信息 -->
    <section class="panel user-panel">
      <div class="avatar">👤</div>
      <div class="user-main">
        <h3>{{ userStore.displayName || '未登录' }}</h3>
        <p>{{ userStore.role || '点击登录后可挂号、查看报告' }}</p>
      </div>
      <el-button v-if="userStore.isLogged" text @click="handleLogout">退出登录</el-button>
      <el-button v-else type="primary" @click="go('Login')">登录</el-button>
    </section>

    <!-- 就诊人 -->
    <section class="panel">
      <div class="panel-title">
        <h4>就诊人管理</h4>
        <el-button text type="primary" @click="go('PatientManage')">管理 ›</el-button>
      </div>

      <EmptyState v-if="!patientStore.patients.length" description="还没有添加就诊人">
        <el-button type="primary" @click="go('PatientManage')">添加就诊人</el-button>
      </EmptyState>

      <div v-else class="patient-list">
        <div
          v-for="item in patientStore.patients"
          :key="item.patientId"
          class="patient-item"
          :class="{ active: item.patientId === patientStore.currentPatientId }"
          @click="patientStore.selectPatient(item.patientId)"
        >
          <span class="p-name">{{ item.name }}</span>
          <span class="p-relation">{{ RELATION_LABEL[item.relation] || item.relation }}</span>
          <el-tag v-if="item.patientId === patientStore.currentPatientId" size="small" type="success">
            当前
          </el-tag>
        </div>
      </div>
    </section>

    <!-- 功能入口 -->
    <section class="panel">
      <div class="panel-title">
        <h4>我的服务</h4>
      </div>

      <div class="entry-grid">
        <div v-for="item in entries" :key="item.name" class="entry-item" @click="go(item.name)">
          <span class="e-icon">{{ item.icon }}</span>
          <div>
            <b>{{ item.text }}</b>
            <p>{{ item.desc }}</p>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped lang="less">
.page {
  .page-container();
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.panel {
  padding: 20px;
  .card();
}

.panel-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;

  h4 {
    font-size: 16px;
  }
}

.user-panel {
  display: flex;
  align-items: center;
  gap: 16px;
}

.avatar {
  width: 56px;
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: var(--primary-light);
  font-size: 26px;
}

.user-main {
  flex: 1;

  h3 {
    font-size: 18px;
  }

  p {
    margin-top: 4px;
    font-size: 13px;
    color: var(--text-3);
  }
}

.patient-list {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.patient-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  border: 1px solid var(--line);
  border-radius: var(--radius);
  cursor: pointer;

  &:hover,
  &.active {
    border-color: var(--primary);
    background: var(--primary-light);
  }
}

.p-relation {
  font-size: 12px;
  color: var(--text-3);
}

.entry-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
}

.entry-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px;
  border: 1px solid var(--line);
  border-radius: var(--radius);
  cursor: pointer;

  &:hover {
    border-color: var(--primary);
  }

  b {
    font-size: 14px;
  }

  p {
    margin-top: 2px;
    font-size: 12px;
    color: var(--text-3);
  }
}

.e-icon {
  font-size: 22px;
}

.mq-lg({
  .entry-grid { grid-template-columns: repeat(2, 1fr); }
});

.mq-md({
  .entry-grid { grid-template-columns: 1fr; }
});
</style>
