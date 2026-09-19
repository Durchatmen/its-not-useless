<script setup>
import GoRegisterBtn from './GoRegisterBtn.vue'

defineProps({
  /** API-08 响应中的 triageCard：department / location / doctor / buttonAction */
  card: { type: Object, default: null },
  disabled: { type: Boolean, default: false },
})
</script>

<template>
  <div v-if="card" class="triage-card">
    <div class="card-head">
      <span class="icon">🩺</span>
      <span class="title">推荐就诊科室</span>
    </div>

    <div class="card-body">
      <div class="row">
        <span class="label">科室</span>
        <span class="value strong">{{ card.department || '—' }}</span>
      </div>
      <div class="row">
        <span class="label">位置</span>
        <span class="value">{{ card.location || '—' }}</span>
      </div>
      <div class="row">
        <span class="label">推荐医生</span>
        <span class="value">{{ card.doctor || '—' }}</span>
      </div>
    </div>

    <div class="card-foot">
      <GoRegisterBtn
        :action="card.buttonAction"
        :department="card.department"
        :disabled="disabled"
      />
    </div>
  </div>
</template>

<style scoped lang="less">
.triage-card {
  margin-top: 10px;
  border: 1px solid var(--primary);
  border-radius: var(--radius);
  background: var(--primary-light);
  overflow: hidden;
}

.card-head {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 10px 14px;
  background: var(--primary);
  color: #fff;
  font-weight: 600;

  .icon {
    font-size: 16px;
  }
}

.card-body {
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.row {
  display: flex;
  gap: 12px;
  font-size: 14px;

  .label {
    flex: 0 0 68px;
    color: var(--text-2);
  }

  .value {
    color: var(--text);
    word-break: break-all;
  }

  .strong {
    font-weight: 600;
    color: var(--primary-dark);
  }
}

.card-foot {
  padding: 0 14px 12px;
}
</style>
