<script setup>
/**
 * 院内导航。
 *
 * **先说清楚本页的能力边界**：院内导航（API-21 楼层平面图路径）不在本期实现范围，
 * 后端没有 /navigation/indoor 路由（原先 API 层留着的 getIndoorNavigation 调它会 404，
 * 已从 frontend/src/api/navigation.js 下线）。没有楼层平面图数据，就画不出引导线，
 * 所以本页不做假的实景地图，只做三件真事：
 *
 *   1. 消费 API-26 下发的 indoorNavUrl 里的 targetCode / floor（检查指引点「院内导航」过来）；
 *   2. 允许从「我的检查单」直接取楼栋 / 楼层 / 房间定位；
 *   3. 把目标位置与到院动线摆清楚，并如实说明实景导引尚未实现。
 */
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import * as examApi from '@/api/exams'
import EmptyState from '@/components/common/EmptyState.vue'
import PageHeader from '@/components/common/PageHeader.vue'
import IndoorFloorMap from '@/components/navigation/IndoorFloorMap.vue'

const route = useRoute()
const router = useRouter()

/** 目标位置：进入页面时先用 query 里的（来自检查指引），也可以手动填或从检查单选 */
const target = ref({
  targetCode: String(route.query.targetCode || ''),
  floor: String(route.query.floor || ''),
  building: String(route.query.building || ''),
  room: String(route.query.room || ''),
  label: String(route.query.fullAddress || route.query.deptName || ''),
})

const exams = ref([])
const loadingExams = ref(false)
const selectedExamId = ref('')

const hasTarget = computed(() =>
  Boolean(target.value.targetCode || target.value.floor || target.value.building || target.value.room),
)

/** 到院后的通用动线，和挂号 / 检查流程一致，不是编造的院内路线 */
const steps = computed(() => [
  { title: '到院', desc: '从门诊大厅入口进院，先完成安检 / 测温' },
  { title: '取号或报到', desc: '有预约的在自助机取号；检查单请先到对应科室分诊台报到' },
  {
    title: target.value.floor ? `乘电梯至 ${target.value.floor}` : '乘电梯至目标楼层',
    desc: target.value.building ? `${target.value.building} 电梯厅，按楼层指引上楼` : '按现场楼层指引上楼',
  },
  {
    title: target.value.room ? `找到 ${target.value.room}` : '找到目标诊室 / 检查室',
    desc: target.value.label || '查看门口标识，或到导医台询问',
  },
  { title: '候诊等待叫号', desc: '在候诊区等待叫号，留意屏幕与叫号提醒' },
])

/** 从检查单的 indoorNavUrl 里解析 targetCode / floor（后端拼的 URL，格式见 exam_service.get_location） */
function parseIndoorUrl(url) {
  if (!url) return {}
  const query = url.split('?')[1] || ''
  const params = new URLSearchParams(query)
  return {
    targetCode: params.get('targetCode') || '',
    floor: params.get('floor') || '',
  }
}

async function loadExams() {
  loadingExams.value = true
  try {
    const data = await examApi.listExams({ pageSize: 20 })
    exams.value = data?.list || data || []
  } catch {
    // 取不到检查单不影响本页使用（还有手填和 query 两条路），静默即可
    exams.value = []
  } finally {
    loadingExams.value = false
  }
}

/** 选中检查单后取 API-26 的位置，填进目标位置 */
async function pickExam(examId) {
  if (!examId) return
  try {
    const location = await examApi.getExamLocation(examId)
    const fromUrl = parseIndoorUrl(location.indoorNavUrl)
    target.value = {
      targetCode: fromUrl.targetCode || location.fullAddress || '',
      floor: location.floor || fromUrl.floor || '',
      building: location.building || '',
      room: location.room || '',
      label: location.fullAddress || location.examName || '',
    }
  } catch {
    target.value = { ...target.value, label: '' }
  }
}

function reset() {
  target.value = { targetCode: '', floor: '', building: '', room: '', label: '' }
  selectedExamId.value = ''
}

onMounted(loadExams)
</script>

<template>
  <div class="page">
    <PageHeader title="院内导航" subtitle="按楼栋、楼层、房间定位到院后的去处">
      <template #extra>
        <el-button text type="primary" @click="router.push({ name: 'OutdoorNav' })">
          院外导航
        </el-button>
      </template>
    </PageHeader>

    <div class="panel">
      <div class="picker">
        <el-select
          v-model="selectedExamId"
          placeholder="从我的检查单定位"
          clearable
          filterable
          :loading="loadingExams"
          style="max-width: 320px"
          @change="pickExam"
        >
          <el-option
            v-for="exam in exams"
            :key="exam.examId"
            :label="exam.examName || exam.examId"
            :value="exam.examId"
          />
        </el-select>

        <span class="or">或</span>
        <el-button @click="router.push({ name: 'MyAppointments' })">从我的挂号查科室</el-button>
        <el-button v-if="hasTarget" text @click="reset">清空</el-button>
      </div>

      <div class="manual">
        <el-input v-model="target.targetCode" placeholder="位置编码 / 目的地（targetCode）" style="max-width: 260px" />
        <el-input v-model="target.floor" placeholder="楼层，如 1F" style="max-width: 120px" />
        <el-input v-model="target.building" placeholder="楼栋，如 医技楼" style="max-width: 150px" />
        <el-input v-model="target.room" placeholder="房间，如 CT-2室" style="max-width: 140px" />
      </div>

      <p class="hint">
        位置编码由后端下发（科室的 floor_position）；从检查指引点进来时会自动带上，
        也可以在上面手填或选择一张检查单。
      </p>
    </div>

    <div class="panel">
      <IndoorFloorMap
        v-if="hasTarget"
        :target-code="target.targetCode"
        :floor="target.floor"
        :building="target.building"
        :room="target.room"
        :label="target.label"
        :steps="steps"
      />

      <EmptyState v-else description="还没有选择目的地">
        <el-button type="primary" @click="router.push({ name: 'ReportList' })">去检查报告</el-button>
        <el-button @click="router.push({ name: 'MyAppointments' })">去我的挂号</el-button>
      </EmptyState>
    </div>

    <div class="panel links">
      <h4>需要帮忙？</h4>
      <div class="link-row">
        <el-button text type="primary" @click="router.push({ name: 'ExamGuide', query: { examId: selectedExamId } })">
          检查注意事项
        </el-button>
        <el-button text type="primary" @click="router.push({ name: 'ExamQueue', query: { examId: selectedExamId } })">
          排队进度
        </el-button>
        <el-button text type="primary" @click="router.push({ name: 'AiChat' })">
          问 AI 陪诊小助手
        </el-button>
      </div>
    </div>
  </div>
</template>

<style scoped lang="less">
.page {
  .page-container();
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.panel {
  padding: 20px;
  .card();
}

.picker {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;

  .or {
    font-size: 12px;
    color: var(--text-3);
  }
}

.manual {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 12px;
}

.hint {
  margin-top: 10px;
  font-size: 12px;
  line-height: 1.8;
  color: var(--text-3);
}

.links {
  h4 {
    margin-bottom: 10px;
    font-size: 14px;
    font-weight: 600;
  }

  .link-row {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }
}
</style>
