<script setup>
/**
 * 高德地图容器（API-20 院外导航）。
 *
 * 地图实例按需加载高德 JS API 2.0（composables/useAmap）。**Key 未配置时不静默失败**：
 * 明确显示缺哪个环境变量，并在有 staticMapUrl（服务端静态图）时退化成静态图展示，
 * 让页面在无 Key 的演示环境下依然说得清楚发生了什么。
 */
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { useAmap } from '@/composables/useAmap'

const props = defineProps({
  /** 地图中心点 */
  center: { type: Object, default: null },
  /** [{ longitude, latitude, title }] */
  markers: { type: Array, default: () => [] },
  /** 服务端下发的高德静态图，无 JS Key 时的退化展示 */
  staticMapUrl: { type: String, default: '' },
  height: { type: String, default: '320px' },
})

const container = ref(null)
const status = ref('loading') // loading | ready | failed
const errorText = ref('')

let map = null

async function render() {
  if (!container.value) return
  status.value = 'loading'
  try {
    const { createMap } = useAmap()
    map = await createMap(container.value, {
      zoom: 13,
      center: props.center ? [props.center.longitude, props.center.latitude] : undefined,
    })

    if (window.AMap && props.markers.length) {
      map.add(
        props.markers.map(
          (item) =>
            new window.AMap.Marker({
              position: [item.longitude, item.latitude],
              title: item.title,
            }),
        ),
      )
      // 让所有标记点都落在视野内（只有 1 个点时保持默认缩放）
      if (props.markers.length > 1) map.setFitView()
    }

    status.value = 'ready'
  } catch (err) {
    status.value = 'failed'
    errorText.value = err?.message || '高德地图加载失败'
  }
}

function destroy() {
  map?.destroy?.()
  map = null
}

onMounted(render)
watch(() => [props.center, props.markers], render, { deep: true })
onBeforeUnmount(destroy)
</script>

<template>
  <div class="amap-view">
    <div ref="container" class="map" :style="{ height }" />

    <!-- 地图没起来就把原因摆在明面上，不让用户对着空白猜 -->
    <div v-if="status !== 'ready'" class="overlay" :style="{ height }">
      <el-empty v-if="status === 'loading'" description="地图加载中…" :image-size="70" />

      <div v-else class="failed">
        <el-alert type="warning" :closable="false" show-icon :title="errorText" />
        <p class="hint">
          需要在前端 <code>.env.development</code> 配置 <code>VITE_AMAP_JS_KEY</code>（并配套
          <code>VITE_AMAP_SECURITY_CODE</code>），后端 <code>.env</code> 配置
          <code>AMAP_WEB_KEY</code>，才能加载地图与路径规划。
        </p>

        <el-image v-if="staticMapUrl" :src="staticMapUrl" fit="cover" class="static-map">
          <template #error>
            <div class="static-fallback">静态地图地址暂不可访问</div>
          </template>
        </el-image>
      </div>
    </div>
  </div>
</template>

<style scoped lang="less">
.amap-view {
  position: relative;
  border: 1px solid var(--line);
  border-radius: var(--radius);
  overflow: hidden;
}

.map {
  width: 100%;
}

.overlay {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px;
  background: var(--card);
}

.failed {
  width: 100%;
  max-width: 560px;

  .hint {
    margin-top: 10px;
    font-size: 12px;
    line-height: 1.8;
    color: var(--text-2);

    code {
      padding: 1px 4px;
      font-size: 12px;
      background: var(--bg);
      border-radius: 4px;
    }
  }

  .static-map {
    width: 100%;
    height: 140px;
    margin-top: 12px;
    border-radius: var(--radius);
  }

  .static-fallback {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 100%;
    font-size: 12px;
    color: var(--text-2);
  }
}
</style>
