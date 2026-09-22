<script setup>
/**
 * 支付结果页。
 *
 * 结算金额、票据号等由「我的账单」页结算成功后带过来（API-17 的响应），
 * 本页再用 API-19 查一次第三方支付单的实际状态做交叉核对 ——
 * 医保结算不经过第三方网关，没有支付单，此时只展示结算结果并说明原因。
 */
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import * as paymentApi from '@/api/payments'
import PageHeader from '@/components/common/PageHeader.vue'
import { BILL_STATUS_LABEL, PAY_CHANNEL_LABEL } from '@/constants/enums'
import { formatMoneyText } from '@/utils/format'

const route = useRoute()
const router = useRouter()

const q = route.query
const billId = String(q.billId || '')
const billTitle = String(q.billTitle || '门诊费用')
const paymentId = String(q.paymentId || '')
const paidAmount = Number(q.paidAmount || 0)
const insurancePaid = Number(q.insurancePaid || 0)
const invoiceNo = String(q.invoiceNo || '')
const billStatus = String(q.billStatus || '')

const loading = ref(false)
const payment = ref(null)

/** 支付单状态 → 结果页图标与文案 */
const PAY_STATUS = {
  SUCCESS: { icon: 'success', title: '支付成功' },
  PAYING: { icon: 'warning', title: '支付处理中' },
  FAIL: { icon: 'error', title: '支付失败' },
  CLOSED: { icon: 'info', title: '支付单已关闭' },
}

const view = computed(() => {
  if (!paymentId) {
    return { icon: 'success', title: '结算成功', note: '医保统筹结算不经过第三方支付网关，因此没有支付单号。' }
  }
  const status = payment.value?.payStatus
  return PAY_STATUS[status] || { icon: 'success', title: '支付成功', note: '' }
})

async function load() {
  if (!paymentId) return
  loading.value = true
  try {
    payment.value = await paymentApi.getPayment(paymentId)
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="page">
    <PageHeader title="支付结果" subtitle="缴费是否成功以本页状态为准" />

    <div v-loading="loading" class="panel">
      <el-result :icon="view.icon" :title="view.title" :sub-title="billTitle">
        <template #extra>
          <div class="rows">
            <div class="row">
              <span>账单单号</span><strong>{{ billId || '—' }}</strong>
            </div>
            <div class="row">
              <span>实付金额</span><strong class="amount">{{ formatMoneyText(paidAmount) }}</strong>
            </div>
            <div class="row">
              <span>医保统筹支付</span><strong>{{ formatMoneyText(insurancePaid) }}</strong>
            </div>
            <div v-if="billStatus" class="row">
              <span>账单状态</span><strong>{{ BILL_STATUS_LABEL[billStatus] || billStatus }}</strong>
            </div>
            <div v-if="invoiceNo" class="row">
              <span>电子票据号</span><strong>{{ invoiceNo }}</strong>
            </div>

            <template v-if="paymentId">
              <div class="row">
                <span>支付单号</span><strong>{{ paymentId }}</strong>
              </div>
              <div class="row">
                <span>支付渠道</span>
                <strong>{{ PAY_CHANNEL_LABEL[payment?.channel] || payment?.channel || '—' }}</strong>
              </div>
              <div class="row">
                <span>支付单状态</span>
                <strong>{{ payment?.payStatus || '查询中' }}</strong>
              </div>
              <div v-if="payment?.paidTime" class="row">
                <span>支付时间</span><strong>{{ payment.paidTime }}</strong>
              </div>
            </template>
          </div>

          <p v-if="view.note" class="note">{{ view.note }}</p>

          <div class="actions">
            <el-button type="primary" @click="router.push({ name: 'BillList' })">返回账单列表</el-button>
            <el-button @click="router.push({ name: 'Home' })">回到首页</el-button>
          </div>
        </template>
      </el-result>
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
  display: inline-flex;
  flex-direction: column;
  gap: 10px;
  min-width: 320px;
  text-align: left;
}

.row {
  display: flex;
  justify-content: space-between;
  gap: 24px;
  font-size: 14px;

  span {
    color: var(--text-2);
  }

  .amount {
    color: var(--red);
  }
}

.note {
  margin-top: 16px;
  padding: 10px 12px;
  font-size: 12px;
  color: var(--text-2);
  background: var(--bg);
  border-radius: var(--radius);
}

.actions {
  display: flex;
  justify-content: center;
  gap: 12px;
  margin-top: 20px;
}
</style>
