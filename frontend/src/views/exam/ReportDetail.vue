<script setup>
/**
 * 报告详情。
 *
 * API-27 拿报告原文与指标明细；API-29 是**按需触发**的 AI 解读（要调大模型，
 * 实测约 6 秒），因此不随页面自动发起，由用户点「AI 解读」按钮再请求，
 * 避免每次进页面都白等一轮大模型。
 *
 * 风险等级、建议、免责声明、追问入口全部由服务端下发，前端原样展示。
 */
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import * as examApi from '@/api/exams'
import EmptyState from '@/components/common/EmptyState.vue'
import PageHeader from '@/components/common/PageHeader.vue'
import AbnormalItemList from '@/components/exam/AbnormalItemList.vue'

const route = useRoute()
const router = useRouter()

const examId = String(route.params.examId || '')
const examName = String(route.query.examName || '')

const loading = ref(false)
const report = ref(null)

const analyzing = ref(false)
const analysis = ref(null)

const RISK = {
  LOW: { text: '风险较低', type: 'success' },
  MEDIUM: { text: '需关注', type: 'warning' },
  HIGH: { text: '风险较高', type: 'danger' },
}

const hasReport = computed(() => report.value?.reportStatus === 'REPORTED')

async function load() {
  loading.value = true
  try {
    report.value = await examApi.getExamReport(examId)
  } finally {
    loading.value = false
  }
}

async function analyze() {
  analyzing.value = true
  try {
    analysis.value = await examApi.analyzeExamReport(examId, {})
  } finally {
    analyzing.value = false
  }
}

/** 追问入口：服务端给的 followUpUrl 形如 /ai?scene=REPORT&examId=... */
function goFollowUp() {
  if (analysis.value?.followUpUrl) router.push(analysis.value.followUpUrl)
  else router.push({ name: 'AiChat' })
}

onMounted(load)
</script>

<template>
  <div class="page">
    <PageHeader
      :title="report?.examName || examName || '报告详情'"
      :subtitle="report?.reportTime ? `报告时间 ${report.reportTime}` : '报告尚未生成'"
    >
      <template #extra>
        <el-button text type="primary" @click="router.push({ name: 'ReportList' })">
          返回列表
        </el-button>
      </template>
    </PageHeader>

    <div v-loading="loading" class="panel">
      <EmptyState v-if="!loading && !report" description="未找到该检查报告" />

      <template v-else-if="report">
        <div class="head">
          <div class="head-left">
            <h3>{{ report.examName }}</h3>
            <span class="meta">报告号 {{ report.reportId || '—' }}</span>
          </div>
          <el-tag :type="hasReport ? 'success' : 'info'">
            {{ hasReport ? '已出报告' : '报告未出' }}
          </el-tag>
        </div>

        <!-- 报告未出：说明原因并给出去处，不留空白页 -->
        <EmptyState v-if="!hasReport" description="检查报告尚未生成，请稍后再来查看">
          <el-button type="primary" @click="router.push({ name: 'ExamQueue', query: { examId } })">
            查看排队进度
          </el-button>
        </EmptyState>

        <template v-else>
          <div v-if="report.reportContent" class="conclusion">
            <span class="label">报告结论</span>
            <p>{{ report.reportContent }}</p>
          </div>

          <div class="section">
            <h4>指标明细</h4>
            <AbnormalItemList :items="report.items" />
          </div>

          <div v-if="report.reportImageUrl" class="section">
            <h4>报告影像</h4>
            <el-image
              :src="report.reportImageUrl"
              fit="contain"
              class="report-image"
              :preview-src-list="[report.reportImageUrl]"
            >
              <template #error>
                <div class="image-fallback">影像地址暂不可访问（演示环境为示例域名）</div>
              </template>
            </el-image>
          </div>

          <!-- AI 解读 -->
          <div class="section ai-section">
            <div class="ai-head">
              <h4>AI 报告解读</h4>
              <el-button v-if="!analysis" type="primary" :loading="analyzing" @click="analyze">
                生成解读
              </el-button>
            </div>

            <p v-if="!analysis && !analyzing" class="ai-hint">
              由 AI 结合报告知识库把指标翻译成通俗说明（约需几秒）
            </p>

            <template v-if="analysis">
              <div class="risk-line">
                <el-tag :type="RISK[analysis.riskLevel]?.type || 'info'">
                  {{ RISK[analysis.riskLevel]?.text || analysis.riskLevel }}
                </el-tag>
                <span class="analysis-text">{{ analysis.analysis }}</span>
              </div>

              <div v-if="analysis.abnormalItems?.length" class="sub">
                <h5>异常项解释</h5>
                <AbnormalItemList :items="analysis.abnormalItems" :show-reference="false" />
              </div>

              <div class="sub">
                <h5>健康建议</h5>
                <p class="advice">{{ analysis.advice }}</p>
              </div>

              <div v-if="analysis.sources?.length" class="sub">
                <h5>知识库来源</h5>
                <div v-for="(src, i) in analysis.sources" :key="i" class="source">
                  <strong>{{ src.title }}</strong>
                  <span class="src-file">{{ src.sourceFile }}</span>
                  <p class="snippet">{{ src.snippet }}</p>
                </div>
              </div>

              <p class="disclaimer">{{ analysis.disclaimer }}</p>

              <el-button type="primary" plain @click="goFollowUp">继续追问 AI 医生</el-button>
            </template>
          </div>
        </template>
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

.head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--line);

  h3 {
    font-size: 18px;
    font-weight: 600;
  }

  .meta {
    display: inline-block;
    margin-top: 4px;
    font-size: 12px;
    color: var(--text-3);
  }
}

.conclusion {
  margin-top: 16px;
  padding: 14px 16px;
  background: var(--primary-light);
  border-radius: var(--radius);

  .label {
    font-size: 12px;
    color: var(--text-2);
  }

  p {
    margin-top: 6px;
    font-size: 14px;
    line-height: 1.7;
  }
}

.section {
  margin-top: 22px;

  h4 {
    margin-bottom: 12px;
    font-size: 15px;
    font-weight: 600;
  }
}

.report-image {
  width: 100%;
  max-width: 420px;
  height: 220px;
  border: 1px solid var(--line);
  border-radius: var(--radius);
}

.image-fallback {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  padding: 0 16px;
  font-size: 13px;
  color: var(--text-2);
  text-align: center;
}

.ai-section {
  padding-top: 20px;
  border-top: 1px solid var(--line);
}

.ai-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;

  h4 {
    margin-bottom: 0;
  }
}

.ai-hint {
  font-size: 13px;
  color: var(--text-2);
}

.risk-line {
  display: flex;
  align-items: flex-start;
  gap: 10px;

  .analysis-text {
    flex: 1;
    font-size: 14px;
    line-height: 1.8;
  }
}

.sub {
  margin-top: 18px;

  h5 {
    margin-bottom: 10px;
    font-size: 14px;
    font-weight: 600;
    color: var(--text);
  }
}

.advice {
  font-size: 14px;
  line-height: 1.8;
  white-space: pre-wrap;
}

.source {
  padding: 12px 14px;
  margin-bottom: 10px;
  background: var(--bg);
  border-radius: var(--radius);

  strong {
    font-size: 13px;
  }

  .src-file {
    display: block;
    margin-top: 2px;
    font-size: 12px;
    color: var(--text-3);
  }

  .snippet {
    margin-top: 6px;
    font-size: 13px;
    color: var(--text-2);
    line-height: 1.7;
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
