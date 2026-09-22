import request from './request'

/**
 * API-20 院外导航（高德路径规划）。
 *
 * mode 传小写 'driving'，后端两套写法都收（大写枚举优先），见 backend/app/api/v1/navigation.py。
 */
export function getOutdoorNavigation({ originLng, originLat, mode = 'driving' } = {}) {
  return request.get('/navigation/outdoor', {
    params: { originLng, originLat, mode },
  })
}

/**
 * API-21 院内导航（楼层平面图路径）**已下线**。
 *
 * 后端本期没有 /navigation/indoor 这个路由，调用固定返回 404
 * （见 backend/app/api/v1/navigation.py 的模块说明：前端应下线该调用，或后端后续补实现）。
 * 因此这里不再导出 getIndoorNavigation —— 院内导航页面改为直接消费 API-26
 * 下发的 indoorNavUrl 里的 targetCode / floor 参数，不依赖该接口。
 */
