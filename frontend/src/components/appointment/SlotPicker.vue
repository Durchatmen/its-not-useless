<script setup>
/**
 * 号源时段选择器 —— 渲染某一位医生**某一个日期**下的所有时段。
 * 数据来自 API-10 查询排班与号源（GET /schedules）返回的 ScheduleListItem。
 *
 * 剩余号为 0 的时段置灰不可点；remaining 由后端在扣减号源时维护。
 */
import { formatMoneyText } from '@/utils/format'

defineProps({
  /** 同一医生、同一日期的排班项数组 */
  slots: { type: Array, default: () => [] },
  /** 当前选中的排班ID */
  modelValue: { type: String, default: '' },
})
const emit = defineEmits(['update:modelValue', 'select'])

function pick(slot) {
  if (!slot.remaining) return
  emit('update:modelValue', slot.scheduleId)
  emit('select', slot)
}
</script>

<template>
  <div class="slot-picker">
    <button
      v-for="slot in slots"
      :key="slot.scheduleId"
      type="button"
      class="slot"
      :class="{ active: slot.scheduleId === modelValue, full: !slot.remaining }"
      :disabled="!slot.remaining"
      @click="pick(slot)"
    >
      <span class="time">{{ slot.timeSlot }}</span>
      <span class="rest">{{ slot.remaining ? `余 ${slot.remaining}` : '已满' }}</span>
      <span class="fee">{{ formatMoneyText(slot.fee) }}</span>
    </button>
  </div>
</template>

<style scoped lang="less">
.slot-picker {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.slot {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  min-width: 108px;
  padding: 8px 12px;
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  cursor: pointer;
  transition: all 0.15s;

  .time {
    font-size: 14px;
    font-weight: 600;
    color: var(--text);
  }

  .rest {
    font-size: 12px;
    color: var(--text-2);
  }

  .fee {
    font-size: 12px;
    color: var(--red);
  }

  &:hover:not(:disabled) {
    border-color: var(--primary);
  }

  &.active {
    border-color: var(--primary);
    background: var(--primary-light);
  }

  &.full {
    cursor: not-allowed;
    opacity: 0.55;
  }
}
</style>
