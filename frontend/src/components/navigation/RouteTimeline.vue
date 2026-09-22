<script setup>
/**
 * 路线时间轴（API-20）。
 *
 * 把选中的出行方案拆成可读的几段：出发 → 交通方式与耗时 → 里程/路况/换乘 → 到达医院 → 停车。
 * 高德返回的是各字段的**文案**（durationText / trafficText / transferText），
 * 不是结构化导航步骤，因此这里按字段有没有值来决定显示哪几段，不臆造路书。
 */
import { computed } from 'vue'

const props = defineProps({
  /** RouteOption */
  route: { type: Object, default: null },
  /** ParkingOption[] */
  parkingOptions: { type: Array, default: () => [] },
  /** 目的地名称，如医院名 */
  destination: { type: String, default: '' },
})
const emit = defineEmits(['park'])

const steps = computed(() => {
  const route = props.route
  if (!route) return []

  const list = [{ title: '出发', desc: '从当前位置出发', type: 'primary' }]

  list.push({
    title: `乘坐${route.modeText}`,
    desc: [route.durationText, route.distanceText].filter(Boolean).join(' · ') || '路线规划中',
    type: 'primary',
  })

  if (route.trafficText) list.push({ title: '实时路况', desc: route.trafficText, type: 'info' })
  if (route.transferText) list.push({ title: '换乘方案', desc: route.transferText, type: 'info' })
  if (route.walkDistance)
    list.push({ title: '步行接驳', desc: `需步行约 ${route.walkDistance} 米`, type: 'info' })

  list.push({
    title: `到达${props.destination || '目的地'}`,
    desc: '以现场标识为准，可在院内导航查看具体科室位置',
    type: 'success',
  })

  return list
})
</script>

<template>
  <div class="route-timeline">
    <el-empty v-if="!steps.length" description="选择一种出行方式后展示路线" :image-size="70" />

    <template v-else>
      <el-timeline>
        <el-timeline-item
          v-for="(step, i) in steps"
          :key="i"
          :type="step.type"
          :hollow="i !== 0 && i !== steps.length - 1"
        >
          <strong class="title">{{ step.title }}</strong>
          <p class="desc">{{ step.desc }}</p>
        </el-timeline-item>
      </el-timeline>

      <div v-if="parkingOptions.length" class="parking">
        <h4>停车场</h4>
        <div v-for="lot in parkingOptions" :key="lot.name" class="lot">
          <div class="lot-main">
            <strong>{{ lot.name }}</strong>
            <span class="distance">{{ lot.distanceText }}</span>
          </div>
          <span class="available">{{ lot.availableText }}</span>
          <el-button size="small" text type="primary" @click="emit('park', lot)">导航到这里</el-button>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped lang="less">
.title {
  font-size: 14px;
}

.desc {
  margin-top: 4px;
  font-size: 13px;
  line-height: 1.7;
  color: var(--text-2);
}

.parking {
  margin-top: 16px;
  padding-top: 14px;
  border-top: 1px solid var(--line);

  h4 {
    margin-bottom: 10px;
    font-size: 14px;
    font-weight: 600;
  }
}

.lot {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  margin-bottom: 8px;
  border: 1px solid var(--line);
  border-radius: var(--radius);

  .lot-main {
    flex: 1;
    display: flex;
    align-items: baseline;
    gap: 8px;
    min-width: 0;

    .distance {
      font-size: 12px;
      color: var(--text-2);
    }
  }

  .available {
    font-size: 12px;
    color: var(--text-2);
  }
}
</style>
