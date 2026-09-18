<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'

import { MODULE_LIST } from '@/constants/modules'
import { usePatientStore } from '@/stores/patient'
import { useUserStore } from '@/stores/user'

const router = useRouter()
const userStore = useUserStore()
const patientStore = usePatientStore()

const greeting = computed(() =>
  userStore.isLogged ? `${userStore.displayName || '您好'}，欢迎回来` : '欢迎来到智慧医疗AI辅助系统',
)

const today = new Date().toLocaleDateString('zh-CN', {
  month: 'long',
  day: 'numeric',
  weekday: 'long',
})

// 健康资讯暂为静态内容，后端接入资讯接口后替换
const news = [
  { icon: '💉', bg: 'linear-gradient(135deg,#0e9f8f,#2ec9b4)', t: '秋季流感高发期，这些防护要点请收好', src: '健康时报', views: '1.2万阅读' },
  { icon: '🫀', bg: 'linear-gradient(135deg,#3b82f6,#6366f1)', t: '体检报告里的"窦性心律"是什么意思？', src: '科普中国', views: '8,632阅读' },
  { icon: '🥗', bg: 'linear-gradient(135deg,#f59e0b,#ef4444)', t: '三高人群饮食指南：少油少盐之外还要注意它', src: '人民健康', views: '6,410阅读' },
]

function openModule(module) {
  router.push(module.route)
}

function startTriage() {
  router.push({ name: 'Triage' })
}
</script>

<template>
  <div class="page">
    <!-- 顶部横幅 -->
    <section class="hero">
      <div class="hero-text">
        <h2>{{ greeting }}</h2>
        <p>
          AI 智能预诊上线：描述症状即可获得分诊建议，精准匹配科室与医生<br />
          {{ today }} · 祝您身体健康
        </p>
        <el-button v-if="!userStore.isLogged" type="primary" @click="router.push({ name: 'Login' })">
          立即登录，开启智慧就医 →
        </el-button>
        <el-button v-else type="primary" @click="startTriage">立即体验 AI 预诊 →</el-button>
      </div>
      <span class="hero-avatar">🩺</span>
    </section>

    <!-- 当前就诊人 -->
    <section v-if="patientStore.currentPatient" class="panel patient-bar">
      <span class="label">当前就诊人</span>
      <span class="name">{{ patientStore.currentPatient.name }}</span>
      <span class="relation">{{ patientStore.currentPatient.relation }}</span>
      <el-button text type="primary" @click="router.push({ name: 'PatientManage' })">
        切换
      </el-button>
    </section>

    <!-- 快捷功能 -->
    <section class="panel">
      <div class="panel-title">
        <h3>快捷功能</h3>
        <span>诊疗全流程服务 · 点击进入</span>
      </div>

      <div class="func-grid">
        <div v-for="item in MODULE_LIST" :key="item.key" class="func-item" @click="openModule(item)">
          <div class="fi-ico" :style="{ background: item.bg }">{{ item.icon }}</div>
          <div class="fi-body">
            <b>{{ item.name }}</b>
            <p>{{ item.desc }}</p>
          </div>
        </div>
      </div>
    </section>

    <!-- 健康资讯 -->
    <section class="panel">
      <div class="panel-title">
        <h3>健康资讯</h3>
        <span>更多 ›</span>
      </div>

      <div class="news-grid">
        <div v-for="(item, index) in news" :key="index" class="news-card">
          <div class="n-top" :style="{ background: item.bg }">{{ item.icon }}</div>
          <div class="n-body">
            <h4>{{ item.t }}</h4>
            <p>{{ item.src }} · {{ item.views }}</p>
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

.hero {
  display: flex;
  align-items: center;
  gap: 24px;
  padding: 28px 32px;
  border-radius: var(--radius-lg);
  background: linear-gradient(135deg, var(--primary), #2ec9b4);
  color: #fff;

  h2 {
    font-size: 24px;
  }

  p {
    margin: 10px 0 18px;
    line-height: 1.9;
    opacity: 0.92;
  }
}

.hero-avatar {
  margin-left: auto;
  font-size: 72px;
}

.panel {
  padding: 20px;
  .card();
}

.panel-title {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: 16px;

  h3 {
    font-size: 17px;
  }

  span {
    font-size: 13px;
    color: var(--text-3);
  }
}

.patient-bar {
  display: flex;
  align-items: center;
  gap: 12px;

  .label {
    color: var(--text-2);
    font-size: 13px;
  }

  .name {
    font-weight: 600;
  }

  .relation {
    font-size: 12px;
    color: var(--text-3);
  }

  .el-button {
    margin-left: auto;
  }
}

.func-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
}

.func-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px;
  border: 1px solid var(--line);
  border-radius: var(--radius);
  cursor: pointer;
  transition: all 0.2s;

  &:hover {
    border-color: var(--primary);
    transform: translateY(-2px);
    box-shadow: var(--shadow);
  }
}

.fi-ico {
  flex: 0 0 40px;
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 10px;
  font-size: 20px;
}

.fi-body {
  min-width: 0;

  b {
    display: block;
    font-size: 14px;
  }

  p {
    margin-top: 2px;
    font-size: 12px;
    color: var(--text-3);
    .ellipsis();
  }
}

.news-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
}

.news-card {
  display: flex;
  gap: 12px;
  padding: 12px;
  border: 1px solid var(--line);
  border-radius: var(--radius);
  cursor: pointer;

  &:hover {
    border-color: var(--primary);
  }
}

.n-top {
  flex: 0 0 44px;
  height: 44px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 10px;
  font-size: 20px;
}

.n-body {
  min-width: 0;

  h4 {
    font-size: 14px;
    font-weight: 500;
    .ellipsis-multi(2);
  }

  p {
    margin-top: 4px;
    font-size: 12px;
    color: var(--text-3);
  }
}

.mq-lg({
  .func-grid { grid-template-columns: repeat(2, 1fr); }
  .news-grid { grid-template-columns: 1fr; }
});

.mq-md({
  .hero { padding: 20px; }
  .hero-avatar { display: none; }
  .func-grid { grid-template-columns: 1fr; }
});
</style>
