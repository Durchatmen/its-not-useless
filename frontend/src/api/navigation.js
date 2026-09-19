import request from './request'

/** API-20 院外导航（高德路径规划） */
export function getOutdoorNavigation({ originLng, originLat, mode = 'driving' } = {}) {
  return request.get('/navigation/outdoor', {
    params: { originLng, originLat, mode },
  })
}

/** API-21 院内导航（楼层平面图路径） */
export function getIndoorNavigation({ destDeptId, floor, currentLng, currentLat } = {}) {
  return request.get('/navigation/indoor', {
    params: { destDeptId, floor, currentLng, currentLat },
  })
}
