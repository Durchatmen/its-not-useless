<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'

import PageHeader from '@/components/common/PageHeader.vue'
import { MODULES } from '@/constants/modules'
import { usePatientStore } from '@/stores/patient'

const router = useRouter()
const patientStore = usePatientStore()

const symptom = ref('')
const module = MODULES.triage

const examples = [
  '头痛伴有恶心，持续两天',
  '咳嗽两周，夜间加重',
  '孩子发烧 38.5 度，精神差',
  '右下腹疼痛，按压更痛',
]

function start() {
  const content = symptom.value.trim()
  if (!content) return
  // 症状作为 query 带入会话页，由该页发起 API-08 流式请求
  router.push({ name: 'AiChat', query: { symptom: content } })
}
</script>

<template>
  <div class="page">
    <PageHeader
      :title="module.name"
      :subtitle="module.desc"
      :back="false"
    />

    <el-alert
      class="risk-tip"
      type="error"
      :closable="false"
      show-icon
      title="如出现胸痛、呼吸困难、意识不清、大出血等急危重症，请立即拨打 120 或前往急诊科。"
    />

    <section class="panel">
      <h4>描述您的症状</h4>
      <p class="hint">建议包含：部位 + 持续时间 + 伴随症状，描述越具体分诊越准确</p>

      <el-input
        v-model="symptom"
        type="textarea"
        :rows="4"
        maxlength="500"
        show-word-limit
        placeholder="例如：头痛伴有恶心，持续两天，无发热"
      />

      <div class="examples">
        <span class="label">示例：</span>
        <el-tag
          v-for="item in examples"
          :key="item"
          class="example-tag"
          effect="plain"
          @click="symptom = item"
        >
          {{ item }}
        </el-tag>
      </div>

      <div v-if="patientStore.currentPatient" class="patient-hint">
        本次预诊针对就诊人：<b>{{ patientStore.currentPatient.name }}</b>
      </div>

      <el-button type="primary" size="large" :disabled="!symptom.trim()" @click="start">
        开始 AI 预诊
      </el-button>
    </section>

    <section class="panel">
      <h4>AI 会帮您做什么</h4>
      <ul class="feat-list">
        <li v-for="item in module.feats" :key="item.t">
          <b>{{ item.t }}</b>
          <span>{{ item.d }}</span>
        </li>
      </ul>
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

.risk-tip {
  margin-bottom: 4px;
}

.panel {
  padding: 20px;
  .card();

  h4 {
    font-size: 16px;
  }
}

.hint {
  margin: 6px 0 14px;
  font-size: 13px;
  color: var(--text-3);
}

.examples {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin: 14px 0;

  .label {
    font-size: 13px;
    color: var(--text-3);
  }
}

.example-tag {
  cursor: pointer;
}

.patient-hint {
  margin-bottom: 16px;
  font-size: 13px;
  color: var(--text-2);
}

.feat-list {
  margin: 12px 0 0;
  padding-left: 18px;
  line-height: 2;

  b {
    margin-right: 8px;
  }

  span {
    color: var(--text-2);
    font-size: 13px;
  }
}
</style>
