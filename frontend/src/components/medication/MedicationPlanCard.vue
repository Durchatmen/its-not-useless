<script setup>
/**
 * 处方卡片 —— 展示一次处方的药品明细（API-30 查询当前处方）。
 * 纯展示组件；「生成用药提醒」「查看药品百科」以事件抛给页面。
 */
import { formatMoneyText } from '@/utils/format'

defineProps({
  /** PrescriptionDetail：prescriptionId/visitDate/deptName/doctorName/金额/drugs */
  prescription: { type: Object, required: true },
})
const emit = defineEmits(['generate', 'wiki'])

const INSURANCE_TAG = { 甲类: 'success', 乙类: 'warning', 丙类: 'info' }
</script>

<template>
  <div class="plan-card">
    <div class="head">
      <div class="head-left">
        <h3>处方 {{ prescription.prescriptionId }}</h3>
        <p class="meta">
          {{ prescription.visitDate }} · {{ prescription.deptName }} · {{ prescription.doctorName }}
        </p>
      </div>
      <div class="head-right">
        <div class="amount">{{ formatMoneyText(prescription.totalAmount) }}</div>
        <div class="split">
          医保 {{ formatMoneyText(prescription.insuranceCover) }} · 自付
          {{ formatMoneyText(prescription.selfPay) }}
        </div>
      </div>
    </div>

    <div class="drugs">
      <div v-for="drug in prescription.drugs" :key="drug.drugId" class="drug">
        <div class="drug-head">
          <div class="name-line">
            <strong>{{ drug.drugName }}</strong>
            <el-tag v-if="drug.insuranceType" size="small" :type="INSURANCE_TAG[drug.insuranceType] || 'info'">
              {{ drug.insuranceType }}
            </el-tag>
          </div>
          <span class="spec">{{ drug.specification }}</span>
        </div>

        <div class="drug-tags">
          <el-tag v-if="drug.dosage" size="small" effect="plain">单次 {{ drug.dosage }}</el-tag>
          <el-tag v-if="drug.frequency" size="small" effect="plain">{{ drug.frequency }}</el-tag>
          <el-tag v-if="drug.usage" size="small" effect="plain">{{ drug.usage }}</el-tag>
          <el-tag v-if="drug.days" size="small" effect="plain">疗程 {{ drug.days }} 天</el-tag>
        </div>

        <p v-if="drug.instructions" class="drug-note">
          <span class="label">用法用量</span>{{ drug.instructions }}
        </p>
        <p v-if="drug.contraindication" class="drug-note warn">
          <span class="label">禁忌与副作用</span>{{ drug.contraindication }}
        </p>
      </div>
    </div>

    <div class="actions">
      <el-button type="primary" @click="emit('generate', prescription)">生成用药提醒</el-button>
      <el-button @click="emit('wiki', prescription)">药品百科</el-button>
    </div>
  </div>
</template>

<style scoped lang="less">
.plan-card {
  padding: 20px;
  .card();
}

.head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--line);

  h3 {
    font-size: 16px;
    font-weight: 600;
  }

  .meta {
    margin-top: 4px;
    font-size: 13px;
    color: var(--text-2);
  }
}

.head-right {
  flex: 0 0 auto;
  text-align: right;

  .amount {
    font-size: 18px;
    font-weight: 600;
    color: var(--red);
  }

  .split {
    margin-top: 4px;
    font-size: 12px;
    color: var(--text-2);
  }
}

.drugs {
  display: flex;
  flex-direction: column;
  gap: 14px;
  margin-top: 16px;
}

.drug {
  padding: 14px 16px;
  border: 1px solid var(--line);
  border-radius: var(--radius);
}

.drug-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;

  .name-line {
    display: flex;
    align-items: center;
    gap: 8px;

    strong {
      font-size: 15px;
    }
  }

  .spec {
    font-size: 12px;
    color: var(--text-3);
  }
}

.drug-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 10px;
}

.drug-note {
  margin-top: 10px;
  font-size: 13px;
  line-height: 1.7;
  color: var(--text-2);

  .label {
    margin-right: 6px;
    color: var(--text-3);
  }

  &.warn {
    color: #b45309;
  }
}

.actions {
  display: flex;
  gap: 12px;
  margin-top: 18px;
  padding-top: 16px;
  border-top: 1px solid var(--line);
}

.mq-md({
  .head { flex-direction: column; }
  .head-right { text-align: left; }
});
</style>
