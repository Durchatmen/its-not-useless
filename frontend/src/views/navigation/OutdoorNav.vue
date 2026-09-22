<script setup>
/**
 * 院外导航（API-20，高德路径规划）。
 *
 * 起点按优先级取：浏览器定位 → 用户手填坐标 → 内置演示坐标（杭州东站）。
 * 定位失败/被拒绝时不报死，退回手填，保证演示环境下页面仍然可用。
 *
 * ⚠ 高德 Key 未配置时后端返回 5004「未配置高德地图 Key（AMAP_WEB_KEY）」，
 * 本页把这个状态原样呈现并说明要配哪个变量，而不是显示空白地图。
 */
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import * as navigationApi from '@/api/navigation'
import PageHeader from '@/components/common/PageHeader.vue'
import AmapView from '@/components/navigation/AmapView.vue'
import RouteTimeline from '@/components/navigation/RouteTimeline.vue'
import TransportCompare from '@/components/navigation/TransportCompare.vue'
import { ApiError, ERROR_CODE } from '@/utils/errorCode'

const router = useRouter()

/** 内置演示起点：杭州东站（后端 AMAP_CITY=杭州） */
const DEMO_ORIGIN = { longitude: 120.213, latitude: 30.29 }

const origin = ref({ ...DEMO_ORIGIN })
const originLabel = ref('演示坐标（杭州东站）')
const locating = ref(false)
const loading = ref(false)
const data = ref(null)
/** 后端业务错误码：5004 = 高德未配 Key，其余见 errorCode 表 */
const errorCode = ref(null)
/** 出行方式：请求可用小写（后端兼容 driving），响应里的 mode 是大写 DRIVE/BUS/WALK/RIDE */
const mode = ref('DRIVE')

const selectedRoute = computed(
  () =>
    data.value?.routes?.find((route) => route.mode === mode.value) ||
    data.value?.routes?.[0] ||
    null,
)

/** 地图标记：起点 + 目的地（目的地坐标来自响应的 hospitalCoord / destCoord） */
const markers = computed(() => {
  const list = [
    { longitude: origin.value.longitude, latitude: origin.value.latitude, title: '我的位置' },
  ]
  const dest = data.value?.destCoord || data.value?.hospitalCoord
  if (dest?.longitude && dest?.latitude) {
    list.push({ longitude: dest.longitude, latitude: dest.latitude, title: data.value.hospitalName })
  }
  return list
})

const DEST_TYPE_TEXT = { GATE: '医院入口', PARKING: '停车场' }

function locate() {
  if (!navigator.geolocation) {
    ElMessage.warning('当前浏览器不支持定位，请手动填写坐标')
    return
  }

  locating.value = true
  navigator.geolocation.getCurrentPosition(
    (pos) => {
      origin.value = { longitude: pos.coords.longitude, latitude: pos.coords.latitude }
      originLabel.value = '浏览器定位'
      locating.value = false
      load()
    },
    (err) => {
      locating.value = false
      ElMessage.warning(`定位失败（${err.message || '权限被拒绝'}），已保留手填坐标`)
    },
    { timeout: 8000, enableHighAccuracy: false },
  )
}

async function load() {
  if (!origin.value.longitude || !origin.value.latitude) {
    ElMessage.warning('请填写起点经纬度')
    return
  }

  loading.value = true
  errorCode.value = null
  try {
    data.value = await navigationApi.getOutdoorNavigation({
      originLng: origin.value.longitude,
      originLat: origin.value.latitude,
      mode: mode.value,
    })
  } catch (err) {
    data.value = null
    errorCode.value = err instanceof ApiError ? err.code : ERROR_CODE.INTERNAL
  } finally {
    loading.value = false
  }
}

function openAmapApp() {
  if (data.value?.amapNavigationUrl) {
    window.open(data.value.amapNavigationUrl, '_blank')
  } else {
    ElMessage.info('后端未下发高德唤起链接（需先配置 AMAP_WEB_KEY）')
  }
}

onMounted(load)
</script>

<template>
  <div class="page">
    <PageHeader title="院外导航" subtitle="查看来院路线、各交通方式耗时与停车场">
      <template #extra>
        <el-button text type="primary" @click="router.push({ name: 'IndoorNav' })">
          院内导航
        </el-button>
      </template>
    </PageHeader>

    <div class="panel origin-panel">
      <div class="origin-row">
        <span class="label">起点</span>
        <el-input-number
          v-model="origin.longitude"
          :precision="6"
          :step="0.001"
          :controls="false"
          placeholder="经度"
          style="width: 130px"
        />
        <el-input-number
          v-model="origin.latitude"
          :precision="6"
          :step="0.001"
          :controls="false"
          placeholder="纬度"
          style="width: 130px"
        />
        <el-button :loading="locating" @click="locate">使用我的定位</el-button>
        <el-button type="primary" :loading="loading" @click="load">规划路线</el-button>
        <span class="origin-label">{{ originLabel }}</span>
      </div>
      <p class="hint">
        浏览器定位不可用时手填经纬度即可；默认值为演示坐标（后端默认城市为杭州）。
      </p>
    </div>

    <!-- 高德未配 Key：说明清楚，不留空白 -->
    <div v-if="errorCode === ERROR_CODE.AMAP_FAILED" class="panel">
      <el-alert
        type="warning"
        :closable="false"
        show-icon
        title="高德地图未配置，暂时无法规划路线"
      />
      <p class="config-hint">
        后端返回 5004：未配置 <code>AMAP_WEB_KEY</code>。请在后端 <code>.env</code> 填入
        <code>AMAP_WEB_KEY</code>，前端 <code>.env.development</code> 填入
        <code>VITE_AMAP_JS_KEY</code> 与 <code>VITE_AMAP_SECURITY_CODE</code> 后重试。
      </p>
    </div>

    <div v-else-if="data" class="body">
      <div class="panel summary">
        <div class="summary-main">
          <h3>{{ data.hospitalName }}</h3>
          <p class="distance">{{ data.distanceText }}</p>
          <!-- 响应里没有医院地址字段，只有目的地类型与坐标（destType / destCoord） -->
          <p class="address">
            <el-tag v-if="data.destType" size="small" effect="plain">
              {{ DEST_TYPE_TEXT[data.destType] || data.destType }}
            </el-tag>
            <span v-if="data.destCoord" class="coord">
              目的地坐标 {{ data.destCoord.longitude }}, {{ data.destCoord.latitude }}
            </span>
          </p>
        </div>
        <el-button type="primary" @click="openAmapApp">一键唤起高德导航</el-button>
      </div>

      <AmapView
        class="panel"
        :center="origin"
        :markers="markers"
        :static-map-url="data.staticMapUrl || ''"
      />

      <div class="panel">
        <h4 class="block-title">出行方式对比</h4>
        <TransportCompare v-model="mode" :routes="data.routes || []" @select="load" />
      </div>

      <div class="panel">
        <h4 class="block-title">路线详情</h4>
        <RouteTimeline :route="selectedRoute" :parking-options="data.parkingOptions || []" :destination="data.hospitalName" />
      </div>
    </div>

    <div v-else-if="loading" class="panel loading-panel">正在规划路线…</div>

    <div v-else class="panel">
      <el-empty description="尚未获取到路线" :image-size="90">
        <el-button type="primary" @click="load">重新规划</el-button>
      </el-empty>
    </div>
  </div>
</template>

<style scoped lang="less">
.page {
  .page-container();
}

.body {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.panel {
  padding: 20px;
  .card();
}

.origin-panel {
  margin-bottom: 16px;
}

.origin-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;

  .label {
    font-size: 13px;
    color: var(--text-2);
  }

  .origin-label {
    font-size: 12px;
    color: var(--text-3);
  }
}

.hint {
  margin-top: 8px;
  font-size: 12px;
  color: var(--text-3);
}

.config-hint {
  margin-top: 12px;
  font-size: 13px;
  line-height: 1.8;
  color: var(--text-2);

  code {
    padding: 1px 4px;
    font-size: 12px;
    background: var(--bg);
    border-radius: 4px;
  }
}

.summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;

  h3 {
    font-size: 16px;
    font-weight: 600;
  }

  .distance {
    margin-top: 6px;
    font-size: 14px;
    color: var(--primary);
  }

  .address {
    margin-top: 4px;
    font-size: 13px;
    color: var(--text-2);
  }
}

.block-title {
  margin-bottom: 14px;
  font-size: 15px;
  font-weight: 600;
}

.loading-panel {
  text-align: center;
  color: var(--text-2);
}

.mq-md({
  .summary { flex-direction: column; align-items: flex-start; }
  .origin-row { flex-direction: column; align-items: stretch; }
});
</style>
