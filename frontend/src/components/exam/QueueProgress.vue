<script setup>
/**
 * 排队进度 —— 把「检查状态进度条」和「现场叫号信息」合成一个组件。
 *
 *   steps  API-28 检查状态查询的 steps（整条流水线：待缴费→待检查→待报告→已报告）
 *   queue  API-25 检查叫号的实时叫号信息（我的号/当前号/前方人数/预计等待）
 *
 * 两者分开取：状态来自库里，叫号是实时估算，任一拿到就能渲染，互不阻塞。
 * 预计等待是估算值，estimateNote 由服务端下发，必须原样展示。
 */
import { computed } from 'vue'

const props = defineProps({
  /** ExamStatusData.steps */
  steps: { type: Array, default: () => [] },
  /** ExamQueueData */
  queue: { type: Object, default: null },
})

/** el-steps 的 active 取「当前节点」下标；没有 current 则用 reached 的最大下标 */
const activeIndex = computed(() => {
  const current = props.steps.findIndex((step) => step.current)
  if (current >= 0) return current
  return props.steps.reduce((acc, step, index) => (step.reached ? index : acc), 0)
})

const statusOf = (step) => (step.reached ? 'finish' : 'wait')
</script>

<template>
  <div class="queue-progress">
    <el-steps v-if="steps.length" :active="activeIndex" align-center class="steps">
      <el-step
        v-for="step in steps"
        :key="step.status"
        :title="step.statusDesc"
        :status="statusOf(step)"
      />
    </el-steps>

    <div v-if="queue" class="queue-box" :class="{ idle: !queue.inQueue }">
      <template v-if="queue.inQueue">
        <div class="numbers">
          <div class="num-item highlight">
            <span class="label">我的排队号</span>
            <strong>{{ queue.queueNo || '—' }}</strong>
          </div>
          <div class="num-item">
            <span class="label">当前叫号</span>
            <strong>{{ queue.currentNo || '—' }}</strong>
          </div>
          <div class="num-item">
            <span class="label">前方等待</span>
            <strong>{{ queue.peopleAhead ?? '—' }} 人</strong>
          </div>
          <div class="num-item">
            <span class="label">预计等待</span>
            <strong>{{ queue.estimatedWaitMinutes ?? '—' }} 分钟</strong>
          </div>
        </div>
        <p class="note">{{ queue.estimateNote }}</p>
      </template>

      <p v-else class="idle-text">
        当前不在叫号队列中（待缴费或已完成报告的检查单不参与叫号）
      </p>
    </div>
  </div>
</template>

<style scoped lang="less">
.steps {
  padding: 8px 0 20px;
}

.queue-box {
  padding: 16px;
  background: var(--primary-light);
  border-radius: var(--radius);

  &.idle {
    background: var(--bg);
  }
}

.numbers {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  gap: 12px;
}

.num-item {
  display: flex;
  flex-direction: column;
  gap: 4px;

  .label {
    font-size: 12px;
    color: var(--text-2);
  }

  strong {
    font-size: 18px;
    font-weight: 600;
  }

  &.highlight strong {
    color: var(--primary);
  }
}

.note,
.idle-text {
  margin-top: 12px;
  font-size: 12px;
  color: var(--text-2);
}

.idle-text {
  margin-top: 0;
  font-size: 13px;
}

.mq-md({
  .steps { padding-bottom: 12px; }
});
</style>
