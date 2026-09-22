<script setup>
/**
 * 院内楼层定位卡 —— 说明设计取舍。
 *
 * **不画平面图**：院内导航（API-21 楼层平面图路径）本期没有实现，后端也没有对应的
 * 平面图数据（没有楼栋 CAD / 房间坐标表），任何「绿色引导线」「房间方块」都只能是编的。
 * 所以这个组件不做地图，只把**真实存在的字段**摆清楚：
 *
 *   楼栋 building / 楼层 floor / 房间 room / 位置编码 targetCode / 完整地址 label
 *
 * 数据来源是 API-26 检查位置指引（t_exam / t_department 的存量字段），
 * 以及科室的 floor_position 编码。
 */
import EmptyState from '@/components/common/EmptyState.vue'

const props = defineProps({
  /** 目标位置编码（科室 floor_position，API-26 的 indoorNavUrl 里带的 targetCode） */
  targetCode: { type: String, default: '' },
  /** 楼层文本，如「1F」「3楼」 */
  floor: { type: String, default: '' },
  /** 楼栋，如「医技楼」 */
  building: { type: String, default: '' },
  /** 房间，如「CT-2室」 */
  room: { type: String, default: '' },
  /** 完整位置或科室名，作为标题兜底 */
  label: { type: String, default: '' },
  /** 通用就诊动线（沿用挂号/检查的既有流程，不是编的院内路线） */
  steps: { type: Array, default: () => [] },
})

/** 有没有任何一个能定位的字段 */
const hasTarget = () => Boolean(props.targetCode || props.floor || props.building || props.room || props.label)
</script>

<template>
  <div class="floor-map">
    <EmptyState v-if="!hasTarget()" description="没有可用的位置信息">
      <slot name="empty" />
    </EmptyState>

    <template v-else>
      <div class="target-card">
        <span class="pin">📍</span>
        <div class="target-main">
          <h4>{{ label || targetCode }}</h4>
          <div class="chips">
            <el-tag v-if="building" size="small" effect="plain">{{ building }}</el-tag>
            <el-tag v-if="floor" size="small" type="primary">{{ floor }}</el-tag>
            <el-tag v-if="room" size="small" effect="plain">{{ room }}</el-tag>
          </div>
        </div>
      </div>

      <!-- 楼层条：只画已知的目标楼层，不虚构整栋楼的层数 -->
      <div class="floor-strip">
        <div class="strip-head">
          <span>楼层定位</span>
          <small>仅显示本次目的地的楼层</small>
        </div>
        <div class="strip-body">
          <div class="floor-block active">
            <span class="floor-name">{{ floor || '楼层待确认' }}</span>
            <span class="floor-desc">{{ room || label || '目的地所在楼层' }}</span>
          </div>
          <div class="other-floors">
            <span v-for="n in 3" :key="n" class="floor-block muted">—</span>
          </div>
        </div>
      </div>

      <div v-if="steps.length" class="flow">
        <h4>到院后怎么走</h4>
        <el-steps direction="vertical" :active="steps.length" finish-status="success">
          <el-step v-for="(step, i) in steps" :key="i" :title="step.title" :description="step.desc" />
        </el-steps>
      </div>

      <el-alert
        class="gap-note"
        type="info"
        :closable="false"
        show-icon
        title="院内实景导引（平面图 + 定位 + 引导线）不在本期实现范围"
      >
        <template #default>
          后端没有楼层平面图数据与院内定位接口，本页只提供楼栋 / 楼层 / 房间与位置编码，
          院内具体路线请以现场导视标识、或到导医台 / 分诊台询问为准。
        </template>
      </el-alert>
    </template>
  </div>
</template>

<style scoped lang="less">
.floor-map {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.target-card {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 16px;
  background: var(--primary-light);
  border: 1px solid var(--primary);
  border-radius: var(--radius);

  .pin {
    font-size: 22px;
    line-height: 1.2;
  }

  .target-main {
    min-width: 0;

    h4 {
      font-size: 16px;
      font-weight: 600;
    }
  }

  .chips {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin-top: 8px;
  }
}

.floor-strip {
  padding: 14px 16px;
  border: 1px solid var(--line);
  border-radius: var(--radius);
}

.strip-head {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin-bottom: 12px;

  span {
    font-size: 14px;
    font-weight: 600;
  }

  small {
    font-size: 12px;
    color: var(--text-3);
  }
}

.strip-body {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.floor-block {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border: 1px dashed var(--line);
  border-radius: var(--radius);

  &.active {
    border-style: solid;
    border-color: var(--primary);
    background: var(--primary-light);
  }

  &.muted {
    color: var(--text-3);
    background: var(--bg);
  }

  .floor-name {
    font-size: 14px;
    font-weight: 600;
  }

  .floor-desc {
    font-size: 12px;
    color: var(--text-2);
  }
}

.other-floors {
  display: flex;
  gap: 6px;

  .floor-block {
    flex: 1;
    justify-content: center;
    padding: 6px;
    font-size: 12px;
  }
}

.flow {
  h4 {
    margin-bottom: 12px;
    font-size: 14px;
    font-weight: 600;
  }
}

.gap-note {
  :deep(.el-alert__content) {
    font-size: 12px;
    line-height: 1.8;
  }
}
</style>
