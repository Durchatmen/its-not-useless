<script setup>
/**
 * 医保咨询（API-32）。
 *
 * 与 AI 陪诊小助手（SSE 流式）不同，本接口是**一次性 POST**，响应里直接带回
 * 答案、引用来源、自付预估卡片、下一句建议与免责声明，所以本页自己做多轮会话：
 * 记住 sessionId 往下一轮带，就能在上文基础上追问。
 *
 * ⚠ 知识库未就绪时后端**不报错**（HTTP 200 + code=0），只是 kbReady=false、
 * answer 换成一段能力受限提示（见 backend/app/api/v1/insurance.py 的说明）。
 * 本页据 kbReady 明确挂出提示条，而不是把降级话术当答案展示、让用户以为查到了。
 *
 * ⚠ estimateCard 经常为 null —— 后端只在知识库片段里**显式写出报销比例**时才给数字，
 * 拿不到依据就不编（医保政策数值一律不硬编码）。这里不补默认值。
 */
import { computed, nextTick, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import * as insuranceApi from '@/api/insurance'
import PageHeader from '@/components/common/PageHeader.vue'
import { usePatientStore } from '@/stores/patient'
import { ApiError } from '@/utils/errorCode'

const router = useRouter()
const patientStore = usePatientStore()

const question = ref('')
const asking = ref(false)
/** 会话ID：后端返回后一直带着，实现多轮追问 */
const sessionId = ref('')
/** [{ role: 'user' | 'bot', text, card?, sources?, disclaimer?, nextQuestion? }] */
const messages = ref([])
/** 最近一次回答里 kbReady=false，说明知识库没就绪 */
const kbReady = ref(true)
const bodyRef = ref(null)

const quickQuestions = [
  '门诊挂号费医保能报销吗？',
  '乙类药品和甲类药品报销有什么区别？',
  '起付线是什么意思，怎么算？',
  '本次就诊我需要自付多少？',
]

const canAsk = computed(() => question.value.trim().length > 0 && !asking.value)

async function scrollToBottom() {
  await nextTick()
  const el = bodyRef.value
  if (el) el.scrollTop = el.scrollHeight
}

async function ask(text) {
  const content = (text ?? question.value).trim()
  if (!content) return

  messages.value.push({ role: 'user', text: content })
  question.value = ''
  asking.value = true
  scrollToBottom()

  try {
    const data = await insuranceApi.consultInsurance({
      question: content,
      sessionId: sessionId.value || undefined,
      patientId: patientStore.currentPatient?.patientId,
    })

    sessionId.value = data.sessionId || sessionId.value
    kbReady.value = data.kbReady !== false
    messages.value.push({
      role: 'bot',
      text: data.answer,
      card: data.estimateCard,
      sources: data.sources || [],
      disclaimer: data.disclaimer,
      nextQuestion: data.nextQuestion,
    })
  } catch (err) {
    const message = err instanceof ApiError ? err.message : '医保咨询失败，请稍后重试'
    ElMessage.error(message)
    messages.value.push({ role: 'bot', text: `（本次提问失败：${message}）`, failed: true })
  } finally {
    asking.value = false
    scrollToBottom()
  }
}

function reset() {
  messages.value = []
  sessionId.value = ''
  kbReady.value = true
}

/** 金额展示：后端给的是数值，这里只做千分位，不做任何政策换算 */
function money(value) {
  if (value === null || value === undefined) return '—'
  return `¥${Number(value).toFixed(2)}`
}
</script>

<template>
  <div class="page">
    <PageHeader title="医保咨询" subtitle="基于医保知识库回答，标注引用来源">
      <template #extra>
        <el-button v-if="messages.length" text @click="reset">重新开始</el-button>
        <el-button text type="primary" @click="router.push({ name: 'BillList' })">
          我的账单
        </el-button>
      </template>
    </PageHeader>

    <!-- 知识库未就绪：说清楚是能力受限，不是「查不到」 -->
    <el-alert
      v-if="!kbReady"
      class="kb-alert"
      type="warning"
      :closable="false"
      show-icon
      title="医保知识库检索链路尚未就绪，当前回答仅供参考"
    >
      <template #default>
        后端已接入医保咨询接口，但知识库未入库或检索依赖未就绪（kbReady=false），
        此时返回的是能力受限提示而非真实检索结果。请以当地医保局最新规定与医院医保办答复为准。
      </template>
    </el-alert>

    <div class="panel chat">
      <div ref="bodyRef" class="chat-body">
        <div v-if="!messages.length" class="intro">
          <span class="intro-icon">🏥</span>
          <h4>问我医保报销的问题</h4>
          <p>报销比例、起付线、甲类 / 乙类区别、本次就诊自付金额都可以问。</p>
          <div class="quick-qs">
            <el-button
              v-for="item in quickQuestions"
              :key="item"
              round
              size="small"
              @click="ask(item)"
            >
              {{ item }}
            </el-button>
          </div>
        </div>

        <div v-for="(msg, i) in messages" :key="i" class="msg" :class="msg.role">
          <div class="bubble" :class="{ failed: msg.failed }">
            <p class="text">{{ msg.text }}</p>

            <!-- 自付预估：只在后端给了依据时才渲染，卡片里每个数字都来自接口 -->
            <div v-if="msg.card" class="estimate">
              <div class="est-head">
                <strong>{{ msg.card.itemName }}</strong>
                <el-tag size="small" type="success">
                  报销 {{ msg.card.reimburseRatioLabel || `${msg.card.reimburseRatio}%` }}
                </el-tag>
              </div>
              <div class="est-row">
                <span class="label">预估自付</span>
                <span class="amount">{{ money(msg.card.estimatedSelfPay) }}</span>
              </div>
              <p v-if="msg.card.basis" class="basis">依据：{{ msg.card.basis }}</p>
            </div>

            <!-- 引用来源：接口文档 2.8 要求原样展示 -->
            <div v-if="msg.sources?.length" class="sources">
              <span class="label">引用来源</span>
              <ul>
                <li v-for="(src, si) in msg.sources" :key="si">{{ src }}</li>
              </ul>
            </div>

            <p v-if="msg.disclaimer" class="disclaimer">{{ msg.disclaimer }}</p>

            <el-button
              v-if="msg.nextQuestion"
              class="next-q"
              size="small"
              text
              type="primary"
              @click="ask(msg.nextQuestion)"
            >
              继续问：{{ msg.nextQuestion }}
            </el-button>
          </div>
        </div>

        <div v-if="asking" class="msg bot">
          <div class="bubble pending">正在检索医保知识库…</div>
        </div>
      </div>

      <div class="composer">
        <el-input
          v-model="question"
          type="textarea"
          :rows="2"
          resize="none"
          maxlength="200"
          show-word-limit
          placeholder="例如：阿莫西林医保能报销多少？"
          @keydown.enter.exact.prevent="ask()"
        />
        <el-button type="primary" :disabled="!canAsk" :loading="asking" @click="ask()">
          发送
        </el-button>
      </div>

      <p class="foot-note">
        回答由医保知识库检索生成，具体报销以当地医保局最新规定为准；如有疑问请咨询医院医保办。
      </p>
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

.kb-alert {
  margin-bottom: 16px;
}

.chat-body {
  max-height: 52vh;
  min-height: 220px;
  overflow-y: auto;
  padding-right: 4px;
}

.intro {
  padding: 28px 16px;
  text-align: center;

  .intro-icon {
    font-size: 44px;
  }

  h4 {
    margin: 10px 0 6px;
    font-size: 17px;
  }

  p {
    font-size: 13px;
    color: var(--text-2);
  }

  .quick-qs {
    display: flex;
    flex-wrap: wrap;
    justify-content: center;
    gap: 8px;
    margin-top: 18px;
  }
}

.msg {
  display: flex;
  margin-bottom: 14px;

  &.user {
    justify-content: flex-end;

    .bubble {
      background: var(--primary-light);
      border-color: var(--primary);
    }
  }
}

.bubble {
  max-width: 78%;
  padding: 12px 14px;
  border: 1px solid var(--line);
  border-radius: var(--radius);

  &.failed {
    border-color: #f0b4b4;
  }

  &.pending {
    font-size: 13px;
    color: var(--text-3);
  }

  .text {
    font-size: 14px;
    line-height: 1.8;
    white-space: pre-wrap;
    color: var(--text-1);
  }
}

.estimate {
  margin-top: 12px;
  padding: 12px;
  background: var(--bg);
  border-radius: var(--radius);

  .est-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;

    strong {
      font-size: 14px;
    }
  }

  .est-row {
    display: flex;
    align-items: baseline;
    gap: 10px;
    margin-top: 10px;

    .label {
      font-size: 12px;
      color: var(--text-3);
    }

    .amount {
      font-size: 20px;
      font-weight: 600;
      color: var(--primary);
    }
  }

  .basis {
    margin-top: 8px;
    font-size: 12px;
    line-height: 1.7;
    color: var(--text-2);
  }
}

.sources {
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px dashed var(--line);

  .label {
    font-size: 12px;
    color: var(--text-3);
  }

  ul {
    padding-left: 18px;
    margin-top: 6px;
  }

  li {
    font-size: 12px;
    line-height: 1.8;
    color: var(--text-2);
  }
}

.disclaimer {
  margin-top: 10px;
  font-size: 12px;
  color: var(--text-3);
}

.next-q {
  margin-top: 8px;
  padding-left: 0;
}

.composer {
  display: flex;
  align-items: flex-end;
  gap: 10px;
  padding-top: 14px;
  margin-top: 14px;
  border-top: 1px solid var(--line);
}

.foot-note {
  margin-top: 12px;
  font-size: 12px;
  line-height: 1.7;
  color: var(--text-3);
}

.mq-md({
  .bubble { max-width: 100%; }
});
</style>
