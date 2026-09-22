<script setup>
/**
 * 排班表 —— 把一位医生（或一个科室）的排班按日期分行，每行交给 SlotPicker 渲染。
 * 数据来自 API-10 查询排班与号源（GET /schedules）。
 */
import { computed } from 'vue'

import SlotPicker from './SlotPicker.vue'

const props = defineProps({
  /** ScheduleListItem 数组 */
  schedules: { type: Array, default: () => [] },
  /** 当前选中的排班ID */
  modelValue: { type: String, default: '' },
})
const emit = defineEmits(['update:modelValue', 'select'])

const WEEKDAYS = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']

/** 按就诊日期分组并按日期升序；组内按时段升序 */
const rows = computed(() => {
  const map = new Map()
  for (const item of props.schedules) {
    if (!map.has(item.apptDate)) map.set(item.apptDate, [])
    map.get(item.apptDate).push(item)
  }
  return [...map.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([apptDate, slots]) => ({
      apptDate,
      weekday: WEEKDAYS[new Date(`${apptDate}T00:00:00`).getDay()],
      remaining: slots.reduce((sum, slot) => sum + (slot.remaining || 0), 0),
      slots: [...slots].sort((a, b) => a.timeSlot.localeCompare(b.timeSlot)),
    }))
})

function forward(value) {
  emit('update:modelValue', value)
}
</script>

<template>
  <div class="schedule-table">
    <div v-for="row in rows" :key="row.apptDate" class="day-row">
      <div class="day-label">
        <strong>{{ row.apptDate }}</strong>
        <span>{{ row.weekday }}</span>
        <em>余号 {{ row.remaining }}</em>
      </div>

      <SlotPicker
        :slots="row.slots"
        :model-value="modelValue"
        @update:model-value="forward"
        @select="emit('select', $event)"
      />
    </div>
  </div>
</template>

<style scoped lang="less">
.schedule-table {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.day-row {
  display: flex;
  align-items: flex-start;
  gap: 16px;
  padding-bottom: 14px;
  border-bottom: 1px dashed var(--line);

  &:last-child {
    padding-bottom: 0;
    border-bottom: none;
  }
}

.day-label {
  flex: 0 0 120px;
  display: flex;
  flex-direction: column;
  gap: 2px;

  strong {
    font-size: 14px;
  }

  span {
    font-size: 12px;
    color: var(--text-2);
  }

  em {
    font-size: 12px;
    font-style: normal;
    color: var(--primary);
  }
}

.mq-md({
  .day-row { flex-direction: column; gap: 10px; }
  .day-label { flex: none; flex-direction: row; align-items: baseline; gap: 8px; }
});
</style>
