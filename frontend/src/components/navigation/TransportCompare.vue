<script setup>
/**
 * 交通方式耗时对比（API-20 响应的 routes 数组）。
 * 每种出行方式一张卡：耗时、里程、红绿灯/拥堵、公交换乘摘要、步行距离。
 */
import EmptyState from '@/components/common/EmptyState.vue'

defineProps({
  /** RouteOption[]：mode/modeText/durationText/distanceText/trafficText/transferText/walkDistance */
  routes: { type: Array, default: () => [] },
  /** 当前选中的出行方式 mode */
  modelValue: { type: String, default: '' },
})
const emit = defineEmits(['update:modelValue', 'select'])

/** 与后端 schemas/navigation.py 的 TravelMode 一致，响应里是大写 */
const ICON = {
  DRIVE: '🚗',
  BUS: '🚌',
  WALK: '🚶',
  RIDE: '🚲',
}

function pick(route) {
  emit('update:modelValue', route.mode)
  emit('select', route)
}
</script>

<template>
  <div class="transport-compare">
    <EmptyState v-if="!routes.length" description="暂无出行方案" />

    <div v-else class="grid">
      <div
        v-for="route in routes"
        :key="route.mode"
        class="option"
        :class="{ active: route.mode === modelValue }"
        @click="pick(route)"
      >
        <div class="head">
          <span class="icon">{{ ICON[route.mode] || '🧭' }}</span>
          <strong>{{ route.modeText }}</strong>
        </div>

        <div class="duration">{{ route.durationText || '—' }}</div>

        <div class="details">
          <span v-if="route.distanceText">{{ route.distanceText }}</span>
          <span v-if="route.walkDistance">{{ route.walkDistance }} 米步行</span>
        </div>

        <p v-if="route.trafficText" class="note">{{ route.trafficText }}</p>
        <p v-if="route.transferText" class="note">{{ route.transferText }}</p>
      </div>
    </div>
  </div>
</template>

<style scoped lang="less">
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 12px;
}

.option {
  padding: 14px;
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  cursor: pointer;
  transition: all 0.2s;

  &:hover {
    border-color: var(--primary);
  }

  &.active {
    border-color: var(--primary);
    background: var(--primary-light);
  }
}

.head {
  display: flex;
  align-items: center;
  gap: 6px;

  .icon {
    font-size: 16px;
  }

  strong {
    font-size: 14px;
  }
}

.duration {
  margin-top: 8px;
  font-size: 18px;
  font-weight: 600;
  color: var(--primary);
}

.details {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 6px;
  font-size: 12px;
  color: var(--text-2);
}

.note {
  margin-top: 8px;
  font-size: 12px;
  line-height: 1.6;
  color: var(--text-3);
}

.mq-md({
  .grid { grid-template-columns: 1fr 1fr; }
});
</style>
