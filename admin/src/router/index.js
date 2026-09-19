import { createRouter, createWebHistory } from 'vue-router'

import { routes } from './routes'
import { useAdminUserStore } from '@/stores/user'
import { hasRole } from '@/constants/roles'

const router = createRouter({
  history: createWebHistory(),
  routes,
})

/** 全局前置守卫：独立鉴权 + 角色分流 */
router.beforeEach((to) => {
  document.title = to.meta.title
    ? `${to.meta.title} · 智慧医疗AI辅助系统管理后台`
    : '智慧医疗AI辅助系统管理后台'

  if (to.meta.public) return true

  const userStore = useAdminUserStore()
  if (!userStore.isLogged) {
    return { name: 'AdminLogin', query: { redirect: to.fullPath } }
  }
  if (!hasRole(userStore.role, to.meta.roles)) {
    return { name: 'Dashboard' }
  }
  return true
})

export default router
