<script setup>
/**
 * 设置。
 *
 * 只放**真的能生效**的项，不做摆设开关：
 *   - 大字模式 / 高对比度 → stores/app.js 写 localStorage 并切 html 上的 class（styles/theme.less 生效）
 *   - 通知授权 → Notification API，被拒时提醒会降级成页面内提示（composables/useNotification.js）
 *   - 当前就诊人 → stores/patient.js，挂号 / 报告 / 医保咨询都读它
 *
 * 无障碍两项是需求分析 F4.2 的要求；没有后端设置接口，偏好只存本地，这一点在页面上写明。
 */
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'

import { useAccessibility } from '@/composables/useAccessibility'
import { useNotification } from '@/composables/useNotification'
import PageHeader from '@/components/common/PageHeader.vue'
import { RELATION_LABEL } from '@/constants/enums'
import { useChatStore } from '@/stores/chat'
import { usePatientStore } from '@/stores/patient'
import { useUserStore } from '@/stores/user'

const router = useRouter()
const userStore = useUserStore()
const patientStore = usePatientStore()
const chatStore = useChatStore()

const { largeFont, highContrast, toggleLargeFont, toggleHighContrast } = useAccessibility()
const { supported: notifySupported, permission, requestPermission, notify } = useNotification()

const loadingPatients = ref(false)

const permissionText = computed(() => {
  if (!notifySupported) return '当前浏览器不支持系统通知，提醒会降级为页面内提示'
  return (
    {
      granted: '已授权，可在系统通知栏收到叫号与用药提醒',
      denied: '已拒绝。需在浏览器地址栏的站点设置里重新允许，否则只能页面内提示',
      default: '未授权，点击右侧按钮授权后可收到系统通知',
    }[permission.value] || permission.value
  )
})

async function handleRequestPermission() {
  const result = await requestPermission()
  if (result === 'granted') {
    ElMessage.success('已开启通知')
    notify({ title: '智慧医疗AI辅助系统', body: '通知已开启，叫号与用药提醒会推送到这里' })
  } else if (result === 'unsupported') {
    ElMessage.warning('当前浏览器不支持系统通知')
  } else {
    ElMessage.warning('未获得通知权限，将使用页面内提示')
  }
}

async function handleSelectPatient(patientId) {
  patientStore.selectPatient(patientId)
  ElMessage.success('已切换当前就诊人')
}

async function loadPatients() {
  loadingPatients.value = true
  try {
    await patientStore.fetchPatients()
  } catch {
    // 拦截器已提示
  } finally {
    loadingPatients.value = false
  }
}

async function handleClearChat() {
  chatStore.reset()
  ElMessage.success('已清空本地会话记录')
}

async function handleLogout() {
  try {
    await ElMessageBox.confirm('退出后需要重新登录，确定吗？', '退出登录', { type: 'warning' })
  } catch {
    return
  }
  userStore.logout()
  patientStore.reset()
  chatStore.reset()
  router.push({ name: 'Login' })
}

onMounted(() => {
  if (userStore.isLogged) loadPatients()
})
</script>

<template>
  <div class="page">
    <PageHeader title="设置" subtitle="无障碍偏好、通知授权与账号相关" />

    <!-- 无障碍 -->
    <section class="panel">
      <h4 class="block-title">无障碍</h4>

      <div class="row">
        <div class="row-main">
          <strong>大字模式</strong>
          <p>整体放大字号，方便老年患者阅读</p>
        </div>
        <el-switch
          :model-value="largeFont"
          @update:model-value="toggleLargeFont"
        />
      </div>

      <div class="row">
        <div class="row-main">
          <strong>高对比度</strong>
          <p>提高文字与背景对比度，弱视环境下更清晰</p>
        </div>
        <el-switch
          :model-value="highContrast"
          @update:model-value="toggleHighContrast"
        />
      </div>

      <p class="note">
        两项偏好保存在本机浏览器（localStorage），换设备或清除浏览器数据后需重新设置。
      </p>
    </section>

    <!-- 通知 -->
    <section class="panel">
      <h4 class="block-title">通知授权</h4>

      <div class="row">
        <div class="row-main">
          <strong>系统通知</strong>
          <p>{{ permissionText }}</p>
        </div>
        <el-button
          v-if="notifySupported && permission !== 'granted'"
          type="primary"
          @click="handleRequestPermission"
        >
          开启通知
        </el-button>
        <el-tag v-else-if="permission === 'granted'" type="success">已开启</el-tag>
      </div>

      <p class="note">
        叫号提醒、检查报告出来、用药到点都会走通知；未授权时降级为页面内提示，不会静默丢失。
      </p>
    </section>

    <!-- 当前就诊人 -->
    <section class="panel">
      <h4 class="block-title">当前就诊人</h4>

      <div v-loading="loadingPatients">
        <p v-if="!patientStore.patients.length" class="empty-line">
          还没有就诊人，
          <el-button text type="primary" @click="router.push({ name: 'PatientManage' })">
            去添加
          </el-button>
        </p>

        <div v-else class="patient-row">
          <el-radio-group
            :model-value="patientStore.currentPatientId"
            @update:model-value="handleSelectPatient"
          >
            <el-radio v-for="item in patientStore.patients" :key="item.patientId" :value="item.patientId">
              {{ item.name }}
              <span class="relation">{{ RELATION_LABEL[item.relation] || item.relationDesc || '' }}</span>
            </el-radio>
          </el-radio-group>
          <el-button text type="primary" @click="router.push({ name: 'PatientManage' })">
            管理就诊人
          </el-button>
        </div>
      </div>
    </section>

    <!-- 账号 -->
    <section class="panel">
      <h4 class="block-title">账号与数据</h4>

      <div class="row">
        <div class="row-main">
          <strong>当前账号</strong>
          <p>{{ userStore.displayName || '未登录' }}<span v-if="userStore.role"> · {{ userStore.role }}</span></p>
        </div>
        <el-button v-if="userStore.isLogged" @click="handleLogout">退出登录</el-button>
        <el-button v-else type="primary" @click="router.push({ name: 'Login' })">登录</el-button>
      </div>

      <div class="row">
        <div class="row-main">
          <strong>本地会话记录</strong>
          <p>清空本机缓存的 AI 对话内容，不影响服务器上的就诊数据</p>
        </div>
        <el-button @click="handleClearChat">清空</el-button>
      </div>
    </section>

    <p class="version">智慧医疗AI辅助系统 · 前端演示版 · 服务地址见 .env.development</p>
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

.block-title {
  margin-bottom: 14px;
  font-size: 15px;
  font-weight: 600;
}

.row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 12px 0;
  border-bottom: 1px dashed var(--line);

  &:last-of-type {
    border-bottom: none;
  }

  .row-main {
    min-width: 0;

    strong {
      font-size: 14px;
    }

    p {
      margin-top: 4px;
      font-size: 12px;
      line-height: 1.7;
      color: var(--text-2);
    }
  }
}

.note,
.version {
  margin-top: 10px;
  font-size: 12px;
  line-height: 1.7;
  color: var(--text-3);
}

.version {
  text-align: center;
}

.empty-line {
  font-size: 13px;
  color: var(--text-2);
}

.patient-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 10px;

  .relation {
    margin-left: 4px;
    font-size: 12px;
    color: var(--text-3);
  }
}
</style>
