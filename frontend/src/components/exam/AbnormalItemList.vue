<script setup>
/**
 * 报告指标列表 —— 每行一个指标，异常值（HIGH/LOW）标红/标蓝并给出通俗解释。
 *
 * 同时吃两种数据源，字段名一致、只是详尽程度不同：
 *   API-27 报告明细 items      {itemName, value, unit, referenceRange, abnormalFlag}
 *   API-29 AI 解读 abnormalItems 同上 + {meaning}
 * 有 meaning 就多渲染一行解释，没有就只显示数值。
 */
import { computed } from 'vue'

import EmptyState from '@/components/common/EmptyState.vue'

const props = defineProps({
  items: { type: Array, default: () => [] },
  /** 是否显示参考范围列（AI 解读结果里没有该字段时自动隐藏） */
  showReference: { type: Boolean, default: true },
})

const FLAG = {
  NORMAL: { text: '正常', type: 'info' },
  HIGH: { text: '偏高', type: 'danger' },
  LOW: { text: '偏低', type: 'warning' },
}

const abnormalCount = computed(
  () => props.items.filter((item) => item.abnormalFlag && item.abnormalFlag !== 'NORMAL').length,
)

const hasReference = computed(() =>
  props.items.some((item) => item.referenceRange),
)
</script>

<template>
  <div class="abnormal-list">
    <EmptyState v-if="!items.length" description="暂无检查指标" />

    <template v-else>
      <div class="summary">
        共 {{ items.length }} 项
        <span v-if="abnormalCount" class="abnormal">，其中 {{ abnormalCount }} 项异常</span>
        <span v-else class="normal">，均在参考范围内</span>
      </div>

      <div class="rows">
        <div
          v-for="item in items"
          :key="item.itemName"
          class="row"
          :class="`flag-${(item.abnormalFlag || 'NORMAL').toLowerCase()}`"
        >
          <div class="main">
            <div class="name-line">
              <strong>{{ item.itemName }}</strong>
              <el-tag size="small" :type="FLAG[item.abnormalFlag || 'NORMAL'].type">
                {{ FLAG[item.abnormalFlag || 'NORMAL'].text }}
              </el-tag>
            </div>

            <div class="value-line">
              <span class="value">{{ item.value ?? '—' }}</span>
              <span v-if="item.unit" class="unit">{{ item.unit }}</span>
              <span v-if="showReference && hasReference" class="ref">
                参考范围 {{ item.referenceRange || '—' }}
              </span>
            </div>

            <p v-if="item.meaning" class="meaning">{{ item.meaning }}</p>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped lang="less">
.summary {
  margin-bottom: 12px;
  font-size: 13px;
  color: var(--text-2);

  .abnormal {
    color: var(--red);
  }

  .normal {
    color: var(--primary);
  }
}

.rows {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.row {
  padding: 12px 14px;
  border: 1px solid var(--line);
  border-left-width: 3px;
  border-radius: var(--radius);

  &.flag-normal {
    border-left-color: var(--line);
  }

  &.flag-high {
    border-left-color: var(--red);
    background: #fef2f2;
  }

  &.flag-low {
    border-left-color: var(--orange);
    background: #fffbeb;
  }
}

.name-line {
  display: flex;
  align-items: center;
  gap: 8px;

  strong {
    font-size: 14px;
  }
}

.value-line {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin-top: 6px;

  .value {
    font-size: 16px;
    font-weight: 600;
    color: var(--text);
  }

  .unit,
  .ref {
    font-size: 12px;
    color: var(--text-2);
  }
}

.meaning {
  margin-top: 8px;
  padding-top: 8px;
  font-size: 13px;
  color: var(--text-2);
  border-top: 1px dashed var(--line);
}
</style>
