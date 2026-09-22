<script setup>
/**
 * 我的账单（支付模块入口）。
 *
 * 完整支付链路（接口文档 3.5）：
 *   API-16 查账单 → 选渠道
 *     医保   → 直接 API-17 诊间结算（走医保统筹，不经过第三方支付网关）
 *     微信/支付宝 → API-18 发起支付拿支付单 → 用户支付 → API-17 结算（带 paymentId）
 *   → 跳「支付结果」页由 API-19 核对支付状态
 *
 * 演示环境的支付网关返回的是 NATIVE 支付链接（不是真实可扫的二维码），
 * 因此弹窗里展示链接原文本 + 一个「模拟支付完成」按钮，语义上等价于用户扫码付款。
 */
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import * as billApi from '@/api/bills'
import * as paymentApi from '@/api/payments'
import EmptyState from '@/components/common/EmptyState.vue'
import PageHeader from '@/components/common/PageHeader.vue'
import { BILL_STATUS, BILL_STATUS_LABEL, BILL_TYPE, BILL_TYPE_LABEL, PAY_CHANNEL, PAY_CHANNEL_LABEL } from '@/constants/enums'
import { formatMoneyText } from '@/utils/format'

const router = useRouter()

const STATUS_TABS = [
  { value: '', label: '全部' },
  { value: BILL_STATUS.UNPAID, label: BILL_STATUS_LABEL.UNPAID },
  { value: BILL_STATUS.PAID, label: BILL_STATUS_LABEL.PAID },
  { value: BILL_STATUS.REFUNDED, label: BILL_STATUS_LABEL.REFUNDED },
]

const TYPE_TABS = [
  { value: '', label: '全部类型' },
  { value: BILL_TYPE.REGISTRATION, label: BILL_TYPE_LABEL.REGISTRATION },
  { value: BILL_TYPE.TREATMENT, label: BILL_TYPE_LABEL.TREATMENT },
]

/** 医保结算的渠道值单独定义在常量表之外，见后端 PayChannel */
const CHANNELS = [
  { value: 'INSURANCE', label: '医保结算' },
  { value: PAY_CHANNEL.WECHAT, label: PAY_CHANNEL_LABEL[PAY_CHANNEL.WECHAT] },
  { value: PAY_CHANNEL.ALIPAY, label: PAY_CHANNEL_LABEL[PAY_CHANNEL.ALIPAY] },
]

const loading = ref(false)
const list = ref([])
const total = ref(0)
const pageNum = ref(1)
const pageSize = ref(10)
const billStatus = ref('')
const billType = ref('')

/* ---------------- 支付弹窗 ---------------- */
const payVisible = ref(false)
const payBill = ref(null)
const channel = ref(PAY_CHANNEL.WECHAT)
const payment = ref(null)
const submitting = ref(false)

const isInsurance = computed(() => channel.value === 'INSURANCE')

async function load() {
  loading.value = true
  try {
    const data = await billApi.listBills({
      billType: billType.value || undefined,
      billStatus: billStatus.value || undefined,
      pageNum: pageNum.value,
      pageSize: pageSize.value,
    })
    list.value = data?.list || []
    total.value = data?.total || 0
  } finally {
    loading.value = false
  }
}

function resetAndLoad() {
  pageNum.value = 1
  load()
}

function openPay(bill) {
  payBill.value = bill
  channel.value = PAY_CHANNEL.WECHAT
  payment.value = null
  payVisible.value = true
}

/** 切换渠道要作废已创建的支付单，否则会拿旧渠道的单子去结算 */
async function changeChannel(value) {
  if (value === channel.value) return
  channel.value = value
  payment.value = null
}

/** 微信/支付宝：第一步先创建支付单 */
async function createPayment() {
  submitting.value = true
  try {
    payment.value = await paymentApi.createPayment({
      billId: payBill.value.billId,
      channel: channel.value,
      amount: payBill.value.amount,
    })
  } finally {
    submitting.value = false
  }
}

/** 结算：医保直接结，第三方渠道带上支付单ID */
async function settle() {
  submitting.value = true
  try {
    const result = await billApi.settleBill(payBill.value.billId, {
      payChannel: channel.value,
      paymentId: isInsurance.value ? undefined : payment.value?.paymentId,
    })

    payVisible.value = false
    ElMessage.success('缴费成功')
    router.push({
      name: 'PaymentResult',
      query: {
        billId: payBill.value.billId,
        billTitle: payBill.value.billTitle,
        paymentId: payment.value?.paymentId || '',
        paidAmount: String(result?.paidAmount ?? ''),
        insurancePaid: String(result?.insurancePaid ?? ''),
        invoiceNo: result?.invoiceNo || '',
        billStatus: result?.billStatus || '',
      },
    })
    load()
  } finally {
    submitting.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="page">
    <PageHeader title="我的账单" subtitle="挂号费、检查费、药费等门诊费用都在这里结算">
      <template #extra>
        <el-button text type="primary" @click="router.push({ name: 'MyAppointments' })">
          我的挂号
        </el-button>
      </template>
    </PageHeader>

    <div class="panel">
      <div class="filters">
        <div class="tabs">
          <el-button
            v-for="tab in STATUS_TABS"
            :key="tab.value"
            size="small"
            :type="billStatus === tab.value ? 'primary' : 'default'"
            @click="billStatus = tab.value; resetAndLoad()"
          >
            {{ tab.label }}
          </el-button>
        </div>

        <div class="tabs">
          <el-button
            v-for="tab in TYPE_TABS"
            :key="tab.value"
            size="small"
            :type="billType === tab.value ? 'primary' : 'default'"
            @click="billType = tab.value; resetAndLoad()"
          >
            {{ tab.label }}
          </el-button>
        </div>
      </div>

      <div v-loading="loading" class="list">
        <EmptyState v-if="!loading && !list.length" description="暂无账单" />

        <div v-for="bill in list" :key="bill.billId" class="bill">
          <div class="bill-main">
            <div class="line-1">
              <h3>{{ bill.billTitle }}</h3>
              <el-tag size="small" :type="bill.billStatus === BILL_STATUS.PAID ? 'success' : bill.billStatus === BILL_STATUS.REFUNDED ? 'info' : 'danger'">
                {{ BILL_STATUS_LABEL[bill.billStatus] }}
              </el-tag>
            </div>

            <div class="line-2">
              <span>{{ BILL_TYPE_LABEL[bill.billType] }}</span>
              <span>开单时间：{{ bill.createTime }}</span>
              <span v-if="bill.relatedId">关联单号：{{ bill.relatedId }}</span>
            </div>
          </div>

          <div class="bill-side">
            <div class="amount">{{ formatMoneyText(bill.amount) }}</div>
            <div class="split">
              医保 {{ formatMoneyText(bill.insuranceCover) }} · 自付
              <strong>{{ formatMoneyText(bill.selfPay) }}</strong>
            </div>
            <el-button
              v-if="bill.billStatus === BILL_STATUS.UNPAID"
              type="primary"
              size="small"
              @click="openPay(bill)"
            >
              去缴费
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

    <!-- 缴费弹窗 -->
    <el-dialog v-model="payVisible" title="缴费" width="460px">
      <template v-if="payBill">
        <div class="pay-head">
          <span class="title">{{ payBill.billTitle }}</span>
          <strong class="amount">{{ formatMoneyText(payBill.amount) }}</strong>
        </div>

        <div class="pay-split">
          <span>医保预估报销 {{ formatMoneyText(payBill.insuranceCover) }}</span>
          <span>自付 {{ formatMoneyText(payBill.selfPay) }}</span>
        </div>

        <el-form label-width="80px" class="pay-form">
          <el-form-item label="支付方式">
            <el-radio-group :model-value="channel" @change="changeChannel">
              <el-radio v-for="item in CHANNELS" :key="item.value" :value="item.value">
                {{ item.label }}
              </el-radio>
            </el-radio-group>
          </el-form-item>
        </el-form>

        <p v-if="isInsurance" class="hint">
          医保结算直接走统筹账户，不经过微信/支付宝网关，确认后立即完成结算。
        </p>

        <!-- 第三方渠道：先创建支付单，再把渠道返回的支付链接交给用户 -->
        <div v-else-if="payment" class="payment-box">
          <p class="hint">请使用{{ PAY_CHANNEL_LABEL[payment.channel] }}完成支付：</p>
          <code class="pay-url">{{ payment.payParams?.code_url || payment.payParams?.prepay_id || '—' }}</code>
          <p class="hint small">
            支付单 {{ payment.paymentId }}，{{ payment.expireTime }} 前有效。
            演示环境为示例支付网关，链接不可真实扫码，点下方按钮模拟支付完成。
          </p>
        </div>

        <p v-else class="hint">将创建一笔{{ PAY_CHANNEL_LABEL[channel] }}支付单，支付完成后自动结算。</p>
      </template>

      <template #footer>
        <el-button @click="payVisible = false">取消</el-button>
        <el-button v-if="!isInsurance && !payment" type="primary" :loading="submitting" @click="createPayment">
          生成支付单
        </el-button>
        <el-button v-else type="primary" :loading="submitting" @click="settle">
          {{ isInsurance ? '确认医保结算' : '模拟支付完成' }}
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

.filters {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 12px;
  padding-bottom: 16px;
  margin-bottom: 16px;
  border-bottom: 1px solid var(--line);
}

.tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-height: 120px;
}

.bill {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 14px 16px;
  border: 1px solid var(--line);
  border-radius: var(--radius);
}

.bill-main {
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

.line-2 {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  margin-top: 8px;
  font-size: 12px;
  color: var(--text-3);
}

.bill-side {
  flex: 0 0 auto;
  text-align: right;

  .amount {
    font-size: 18px;
    font-weight: 600;
    color: var(--red);
  }

  .split {
    margin: 4px 0 8px;
    font-size: 12px;
    color: var(--text-2);
  }
}

.pager {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}

.pay-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 15px;

  .amount {
    font-size: 20px;
    color: var(--red);
  }
}

.pay-split {
  display: flex;
  gap: 16px;
  margin-top: 8px;
  font-size: 13px;
  color: var(--text-2);
}

.pay-form {
  margin-top: 16px;
}

.hint {
  margin-top: 8px;
  font-size: 13px;
  line-height: 1.7;
  color: var(--text-2);

  &.small {
    font-size: 12px;
    color: var(--text-3);
  }
}

.payment-box {
  margin-top: 8px;
  padding: 12px 14px;
  background: var(--bg);
  border-radius: var(--radius);

  .pay-url {
    display: block;
    margin-top: 8px;
    padding: 8px 10px;
    font-size: 12px;
    word-break: break-all;
    background: var(--card);
    border: 1px solid var(--line);
    border-radius: 6px;
  }
}

.mq-md({
  .bill { flex-direction: column; align-items: stretch; }
  .bill-side { text-align: left; }
});
</style>
