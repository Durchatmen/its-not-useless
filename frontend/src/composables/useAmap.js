/**
 * 高德地图 JS API 2.0 动态加载（技术选型：院外导航、院内地图展示）。
 * 安全密钥已在 main.js 中通过 window._AMapSecurityConfig 注入，
 * 缺失时会报 INVALID_USER_SCODE。
 */
let loading = null

export function useAmap() {
  function load() {
    if (window.AMap) return Promise.resolve(window.AMap)
    if (loading) return loading

    loading = new Promise((resolve, reject) => {
      const key = import.meta.env.VITE_AMAP_JS_KEY
      if (!key) {
        reject(new Error('未配置 VITE_AMAP_JS_KEY，请检查 .env.development'))
        return
      }
      const script = document.createElement('script')
      script.src = `https://webapi.amap.com/maps?v=2.0&key=${key}`
      script.async = true
      script.onload = () =>
        window.AMap ? resolve(window.AMap) : reject(new Error('高德地图初始化失败'))
      script.onerror = () => {
        loading = null
        reject(new Error('高德地图 JS API 加载失败'))
      }
      document.head.appendChild(script)
    })

    return loading
  }

  /** 在指定容器创建地图实例 */
  async function createMap(container, options = {}) {
    const AMap = await load()
    return new AMap.Map(container, options)
  }

  return { load, createMap }
}
