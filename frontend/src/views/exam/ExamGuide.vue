<script setup>
/**
 * 检查指引。
 *
 * API-24 给注意事项（含语音播报文本），API-26 给执行科室的楼栋/楼层/房间，
 * 并下发 indoorNavUrl 指向院内导航（API-21 已从需求范围砍掉，该路由仍是占位页，
 * 这里照常跳转，落地页由导航模块负责）。
 *
 * 语音播报用浏览器原生 speechSynthesis，不依赖任何后端接口，也不产生网络请求。
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import * as examApi from '@/api/exams'
import EmptyState from '@/components/common/EmptyState.vue'
import PageHeader from '@/components/common/PageHeader.vue'

const route = useRoute()
const router = useRouter()

const examId = String(route.query.examId || '')
const examName = String(route.query.examName || '')

const loading = ref(false)
const precautions = ref(null)
const location = ref(null)
const speaking = ref(false)

/** 注意事项按行分条展示 */
const lines = computed(() =>
  (precautions.value?.precautions || '')
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean),
)

const canSpeak = typeof window !== 'undefined' && 'speechSynthesis' in window

function speak() {
  if (!canSpeak || !precautions.value?.voiceText) return

  window.speechSynthesis.cancel()
  const utterance = new SpeechSynthesisUtterance(precautions.value.voiceText)
  utterance.lang = 'zh-CN'
  utterance.onend = () => {
    speaking.value = false
  }
  utterance.onerror = () => {
    speaking.value = false
  }
  speaking.value = true
  window.speechSynthesis.speak(utterance)
}

function stopSpeak() {
  if (!canSpeak) return
  window.speechSynthesis.cancel()
  speaking.value = false
}

async function load() {
  if (!examId) return
  loading.value = true
  try {
    // 两个接口互不依赖，并发取；任一失败不影响另一个渲染
    const [pre, loc] = await Promise.allSettled([
      examApi.getExamPrecautions(examId),
      examApi.getExamLocation(examId),
    ])
    if (pre.status === 'fulfilled') precautions.value = pre.value
    if (loc.status === 'fulfilled') location.value = loc.value
  } finally {
    loading.value = false
  }
}

function goIndoorNav() {
  if (location.value?.indoorNavUrl) router.push(location.value.indoorNavUrl)
  else ElMessage.info('暂无院内导航路线')
}

onMounted(load)
// 离开页面时掐掉播报，否则会跟着用户走到别的页面继续念
onBeforeUnmount(stopSpeak)
</script>

<template>
  <div class="page">
    <PageHeader
      :title="precautions?.examName || examName || '检查指引'"
      subtitle="检查前的准备事项与到院后的去处"
    >
      <template #extra>
        <el-button text type="primary" @click="router.push({ name: 'ReportList' })">
          返回列表
        </el-button>
      </template>
    </PageHeader>

    <div v-loading="loading" class="panel">
      <EmptyState v-if="!examId" description="未指定检查单">
        <el-button type="primary" @click="router.push({ name: 'ReportList' })">去检查列表</el-button>
      </EmptyState>

      <template v-else>
        <div class="block">
          <div class="block-head">
            <h3>检查注意事项</h3>
            <el-button v-if="canSpeak" size="small" :type="speaking ? 'danger' : 'default'" @click="speaking ? stopSpeak() : speak()">
              {{ speaking ? '停止播报' : '语音播报' }}
            </el-button>
          </div>

          <EmptyState v-if="!lines.length" description="暂无注意事项" />
          <ul v-else class="precautions">
            <li v-for="(line, i) in lines" :key="i">{{ line }}</li>
          </ul>

          <div v-if="precautions?.purpose || precautions?.process" class="extra">
            <div v-if="precautions.purpose" class="extra-row">
              <span>检查目的</span>
              <p>{{ precautions.purpose }}</p>
            </div>
            <div v-if="precautions.process" class="extra-row">
              <span>检查流程</span>
              <p>{{ precautions.process }}</p>
            </div>
          </div>
        </div>

        <div class="block">
          <h3>检查地点</h3>

          <EmptyState v-if="!location" description="暂无地点信息" />
          <template v-else>
            <div class="location">
              <div class="loc-main">
                <strong>{{ location.fullAddress }}</strong>
                <span class="dept">{{ location.deptName }}</span>
              </div>
              <div class="loc-tags">
                <el-tag v-if="location.building" size="small" type="info">{{ location.building }}</el-tag>
                <el-tag v-if="location.floor" size="small" type="info">{{ location.floor }}</el-tag>
                <el-tag v-if="location.room" size="small" type="info">{{ location.room }}</el-tag>
              </div>
            </div>

            <div class="loc-actions">
              <el-button type="primary" @click="goIndoorNav">院内导航</el-button>
              <el-button @click="router.push({ name: 'ExamQueue', query: { examId, examName } })">
                查看排队进度
              </el-button>
            </div>
          </template>
        </div>

        <p v-if="precautions?.disclaimer" class="disclaimer">{{ precautions.disclaimer }}</p>
      </template>
    </div>
  </div>
</template>

<style scoped lang="less">
.page {
  .page-container();
}

.panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.block {
  padding: 20px;
  .card();

  h3 {
    font-size: 15px;
    font-weight: 600;
  }
}

.block-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;

  h3 {
    margin-bottom: 0;
  }
}

.precautions {
  padding-left: 20px;
  list-style: disc;

  li {
    margin-bottom: 8px;
    font-size: 14px;
    line-height: 1.7;
    color: var(--text);
  }
}

.extra {
  margin-top: 16px;
  padding-top: 14px;
  border-top: 1px dashed var(--line);
}

.extra-row {
  margin-bottom: 12px;

  span {
    font-size: 12px;
    color: var(--text-2);
  }

  p {
    margin-top: 4px;
    font-size: 14px;
    line-height: 1.7;
    white-space: pre-wrap;
  }
}

.location {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 16px;
  background: var(--primary-light);
  border-radius: var(--radius);

  .loc-main {
    display: flex;
    flex-direction: column;
    gap: 4px;

    strong {
      font-size: 15px;
    }

    .dept {
      font-size: 13px;
      color: var(--text-2);
    }
  }

  .loc-tags {
    display: flex;
    gap: 6px;
  }
}

.loc-actions {
  display: flex;
  gap: 12px;
  margin-top: 14px;
}

.disclaimer {
  padding: 10px 12px;
  font-size: 12px;
  color: var(--text-2);
  background: var(--bg);
  border-radius: var(--radius);
}

.mq-md({
  .location { flex-direction: column; align-items: flex-start; }
});
</style>
