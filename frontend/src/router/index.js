import { createRouter, createWebHistory } from 'vue-router'

import { routes } from './routes'
import { useUserStore } from '@/stores/user'
import { hasRole } from '@/constants/roles'

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior: () => ({ top: 0 }),
})

/** 全局前置守卫：鉴权 + 角色分流（需求分析 9.1 权限矩阵） */
router.beforeEach((to) => {
  document.title = to.meta.title ? `${to.meta.title} · 智慧医疗AI辅助系统` : '智慧医疗AI辅助系统'

  if (to.meta.public) return true

  const userStore = useUserStore()
  if (!userStore.isLogged) {
    return { name: 'Login', query: { redirect: to.fullPath } }
  }
  if (!hasRole(userStore.role, to.meta.roles)) {
    return { name: 'Home' }
  }
  return true
})

export default router
