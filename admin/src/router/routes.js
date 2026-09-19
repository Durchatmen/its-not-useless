import BlankLayout from '@/layouts/BlankLayout.vue'
import AdminLayout from '@/layouts/AdminLayout.vue'
import { ADMIN_ROLE } from '@/constants/roles'

/**
 * 后台路由表。
 * meta.roles 为空表示登录即可访问（管理员与运营均可）。
 * 各页面所需权限与《需求分析》9.1 权限矩阵对应。
 */
export const routes = [
  {
    path: '/login',
    name: 'AdminLogin',
    component: () => import('@/views/login/Login.vue'),
    meta: { title: '登录', public: true },
  },
  {
    path: '/',
    component: AdminLayout,
    redirect: '/dashboard',
    children: [
      { path: 'dashboard', name: 'Dashboard', component: () => import('@/views/dashboard/Index.vue'), meta: { title: '概览' } },

      // 科室 / 医生 / 排班 / 楼层：管理员
      { path: 'catalog/departments', name: 'DeptList', component: () => import('@/views/catalog/DeptList.vue'), meta: { title: '科室维护', roles: [ADMIN_ROLE.ADMIN] } },
      { path: 'catalog/doctors', name: 'DoctorList', component: () => import('@/views/catalog/DoctorList.vue'), meta: { title: '医生维护', roles: [ADMIN_ROLE.ADMIN] } },
      { path: 'catalog/schedules', name: 'ScheduleList', component: () => import('@/views/catalog/ScheduleList.vue'), meta: { title: '排班维护', roles: [ADMIN_ROLE.ADMIN] } },
      { path: 'catalog/floors', name: 'FloorMap', component: () => import('@/views/catalog/FloorMap.vue'), meta: { title: '楼层平面图', roles: [ADMIN_ROLE.ADMIN] } },

      // 用户与权限：管理员
      { path: 'users', name: 'UserList', component: () => import('@/views/user/UserList.vue'), meta: { title: '用户管理', roles: [ADMIN_ROLE.ADMIN] } },
      { path: 'users/roles', name: 'RoleAssign', component: () => import('@/views/user/RoleAssign.vue'), meta: { title: '权限分配', roles: [ADMIN_ROLE.ADMIN] } },

      // 知识库：管理员
      { path: 'knowledge', name: 'KnowledgeList', component: () => import('@/views/knowledge/KnowledgeList.vue'), meta: { title: '知识库维护', roles: [ADMIN_ROLE.ADMIN] } },
      { path: 'knowledge/upload', name: 'KnowledgeUpload', component: () => import('@/views/knowledge/KnowledgeUpload.vue'), meta: { title: '知识库导入', roles: [ADMIN_ROLE.ADMIN] } },

      // 会话日志与人工兜底：管理员 / 运营
      { path: 'sessions', name: 'SessionLog', component: () => import('@/views/session/SessionLog.vue'), meta: { title: '会话日志' } },
      { path: 'sessions/intervene', name: 'Intervene', component: () => import('@/views/session/Intervene.vue'), meta: { title: '人工兜底', roles: [ADMIN_ROLE.OPERATOR] } },

      // 排队监控 / 日志
      { path: 'queues', name: 'QueueMonitor', component: () => import('@/views/queue/QueueMonitor.vue'), meta: { title: '排队监控' } },
      { path: 'logs', name: 'OperationLog', component: () => import('@/views/log/OperationLog.vue'), meta: { title: '操作日志' } },
    ],
  },
  { path: '/:pathMatch(.*)*', redirect: '/dashboard' },
]
