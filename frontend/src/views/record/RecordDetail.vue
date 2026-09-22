<script setup>
/**
 * 病历详情 + AI 通俗解读。
 *
 * 摘要部分复用 API-22 的列表数据按 recordId 反查 —— 后端没有「单条病历查询」接口，
 * 病历详情页只给了 recordId（路由 /record/:recordId），因此从列表里捞；
 * 直接粘 URL 进来也能工作，不必依赖列表页的跳转参数。
 *
 * AI 解读走 API-23，要调大模型（实测约 5~10 秒），所以按需触发而不是进页面就发。
 * interpretation / termMapping / disclaimer 全部由服务端下发，前端原样展示。
 */
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import * as recordApi from '@/api/medicalRecords'
import EmptyState from '@/components/common/EmptyState.vue'
import PageHeader from '@/components/common/PageHeader.vue'

const route = useRoute()
const router = useRouter()

const recordId = String(route.params.recordId || '')

const loading = ref(false)
const record = ref(null)

const interpreting = ref(false)
const result = ref(null)

async function load() {
  loading.value = true
  try {
    const data = await recordApi.listMedicalRecords({ pageNum: 1, pageSize: 100 })
    record.value = (data?.list || []).find((item) => item.recordId === recordId) || null
  } finally {
    loading.value = false
  }
}

async function interpret() {
  interpreting.value = true
  try {
    result.value = await recordApi.interpretRecord({ recordId })
  } finally {
    interpreting.value = false
  }
}

function goFollowUp() {
  if (result.value?.followUpUrl) router.push(result.value.followUpUrl)
  else router.push({ name: 'AiChat' })
}

onMounted(load)
</script>

<template>
  <div class="page">
    <PageHeader
      :title="record?.diagnosis || '病历详情'"
      :subtitle="record ? `${record.visitDate} · ${record.deptName} · ${record.doctorName}` : '加载中'"
    >
      <template #extra>
        <el-button text type="primary" @click="router.push({ name: 'RecordList' })">
          返回列表
        </el-button>
      </template>
    </PageHeader>

    <div v-loading="loading" class="panel">
      <EmptyState v-if="!loading && !record" description="未找到该病历">
        <el-button type="primary" @click="router.push({ name: 'RecordList' })">返回病历列表</el-button>
      </EmptyState>

      <template v-else-if="record">
        <div class="rows">
          <div class="row"><span>就诊人</span><strong>{{ record.patientName }}</strong></div>
          <div class="row"><span>就诊日期</span><strong>{{ record.visitDate }}</strong></div>
          <div class="row"><span>就诊科室</span><strong>{{ record.deptName }}</strong></div>
          <div class="row"><span>接诊医生</span><strong>{{ record.doctorName }}</strong></div>
          <div class="row"><span>诊断结果</span><strong>{{ record.diagnosis }}</strong></div>
          <div class="row"><span>处方摘要</span><strong>{{ record.prescriptionBrief || '—' }}</strong></div>
        </div>

        <div class="ai-section">
          <div class="ai-head">
            <h4>AI 通俗解读</h4>
            <el-button v-if="!result" type="primary" :loading="interpreting" @click="interpret">
              生成解读
            </el-button>
          </div>

          <p v-if="!result && !interpreting" class="ai-hint">
            把病历里的专业术语翻译成日常说法（需调用大模型，约几秒）
          </p>
          <p v-else-if="interpreting" class="ai-hint">正在解读…</p>

          <template v-if="result">
            <p class="interpretation">{{ result.interpretation }}</p>

            <div v-if="result.termMapping?.length" class="terms">
              <h5>术语对照</h5>
              <el-table :data="result.termMapping" size="small" border>
                <el-table-column prop="term" label="专业术语" width="180" />
                <el-table-column prop="plain" label="通俗解释" />
              </el-table>
            </div>

            <div v-if="result.sources?.length" class="sources">
              <h5>引用来源</h5>
              <ul>
                <li v-for="(src, i) in result.sources" :key="i">{{ src }}</li>
              </ul>
            </div>

            <p class="disclaimer">{{ result.disclaimer }}</p>

            <el-button type="primary" plain @click="goFollowUp">继续追问 AI 医生</el-button>
          </template>
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

.rows {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.row {
  display: flex;
  gap: 16px;
  font-size: 14px;

  span {
    flex: 0 0 76px;
    color: var(--text-2);
  }

  strong {
    flex: 1;
    font-weight: 500;
    line-height: 1.6;
  }
}

.ai-section {
  margin-top: 24px;
  padding-top: 20px;
  border-top: 1px solid var(--line);
}

.ai-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;

  h4 {
    font-size: 15px;
    font-weight: 600;
  }
}

.ai-hint {
  font-size: 13px;
  color: var(--text-2);
}

.interpretation {
  padding: 14px 16px;
  font-size: 14px;
  line-height: 1.8;
  background: var(--primary-light);
  border-radius: var(--radius);
}

.terms,
.sources {
  margin-top: 18px;

  h5 {
    margin-bottom: 10px;
    font-size: 14px;
    font-weight: 600;
  }

  ul {
    padding-left: 20px;
    list-style: disc;

    li {
      margin-bottom: 6px;
      font-size: 13px;
      color: var(--text-2);
    }
  }
}

.disclaimer {
  margin: 18px 0 16px;
  padding: 10px 12px;
  font-size: 12px;
  color: var(--text-2);
  background: var(--bg);
  border-radius: var(--radius);
}
</style>
