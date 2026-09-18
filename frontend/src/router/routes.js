import BlankLayout from '@/layouts/BlankLayout.vue'
import DefaultLayout from '@/layouts/DefaultLayout.vue'

/**
 * 路由表。
 * meta.public       —— 免登录
 * meta.roles        —— 允许访问的角色，缺省表示登录即可
 * meta.hideBottomNav / meta.fullscreen —— 布局开关
 */
export const routes = [
  {
    path: '/auth',
    component: BlankLayout,
    children: [
      {
        path: 'login',
        name: 'Login',
        component: () => import('@/views/auth/Login.vue'),
        meta: { title: '登录', public: true },
      },
      {
        path: 'register',
        name: 'Register',
        component: () => import('@/views/auth/Register.vue'),
        meta: { title: '注册', public: true },
      },
    ],
  },
  {
    path: '/',
    component: DefaultLayout,
    redirect: '/home',
    children: [
      { path: 'home', name: 'Home', component: () => import('@/views/home/Home.vue'), meta: { title: '首页' } },

      {
        path: 'ai',
        name: 'AiChat',
        component: () => import('@/views/ai/AIChat.vue'),
        meta: { title: 'AI陪诊小助手', hideBottomNav: true, fullscreen: true },
      },

      // 预诊 + 分诊
      { path: 'triage', name: 'Triage', component: () => import('@/views/triage/Triage.vue'), meta: { title: 'AI 预诊分诊' } },

      // 挂号
      { path: 'appointment/dept', name: 'DeptSelect', component: () => import('@/views/appointment/DeptSelect.vue'), meta: { title: '选择科室' } },
      { path: 'appointment/doctor', name: 'DoctorSelect', component: () => import('@/views/appointment/DoctorSelect.vue'), meta: { title: '选择医生' } },
      { path: 'appointment/confirm', name: 'AppointmentConfirm', component: () => import('@/views/appointment/AppointmentConfirm.vue'), meta: { title: '确认挂号' } },
      { path: 'appointment/mine', name: 'MyAppointments', component: () => import('@/views/appointment/MyAppointments.vue'), meta: { title: '我的挂号' } },

      // 检查与报告
      { path: 'exam/guide', name: 'ExamGuide', component: () => import('@/views/exam/ExamGuide.vue'), meta: { title: '检查指引' } },
      { path: 'exam/queue', name: 'ExamQueue', component: () => import('@/views/exam/ExamQueue.vue'), meta: { title: '排队进度' } },
      { path: 'exam/reports', name: 'ReportList', component: () => import('@/views/exam/ReportList.vue'), meta: { title: '检查报告' } },
      { path: 'exam/reports/:examId', name: 'ReportDetail', component: () => import('@/views/exam/ReportDetail.vue'), meta: { title: '报告详情' } },

      // 病历
      { path: 'record', name: 'RecordList', component: () => import('@/views/record/RecordList.vue'), meta: { title: '电子病历' } },
      { path: 'record/:recordId', name: 'RecordDetail', component: () => import('@/views/record/RecordDetail.vue'), meta: { title: '病历详情' } },

      // 支付
      { path: 'payment/bills', name: 'BillList', component: () => import('@/views/payment/BillList.vue'), meta: { title: '我的账单' } },
      { path: 'payment/result', name: 'PaymentResult', component: () => import('@/views/payment/PaymentResult.vue'), meta: { title: '支付结果' } },

      // 导航
      { path: 'navigation/outdoor', name: 'OutdoorNav', component: () => import('@/views/navigation/OutdoorNav.vue'), meta: { title: '院外导航' } },
      { path: 'navigation/indoor', name: 'IndoorNav', component: () => import('@/views/navigation/IndoorNav.vue'), meta: { title: '院内导航' } },

      // 用药
      { path: 'medication/plan', name: 'MedicationPlan', component: () => import('@/views/medication/MedicationPlan.vue'), meta: { title: '用药计划' } },
      { path: 'medication/reminder', name: 'ReminderSetting', component: () => import('@/views/medication/ReminderSetting.vue'), meta: { title: '提醒设置' } },
      { path: 'medication/wiki', name: 'DrugWiki', component: () => import('@/views/medication/DrugWiki.vue'), meta: { title: '药品百科' } },

      // 医保
      { path: 'insurance', name: 'InsuranceConsult', component: () => import('@/views/insurance/InsuranceConsult.vue'), meta: { title: '医保咨询' } },

      // 我的
      { path: 'profile', name: 'Profile', component: () => import('@/views/profile/Profile.vue'), meta: { title: '我的' } },
      { path: 'profile/patients', name: 'PatientManage', component: () => import('@/views/profile/PatientManage.vue'), meta: { title: '就诊人管理' } },
      { path: 'profile/settings', name: 'Settings', component: () => import('@/views/profile/Settings.vue'), meta: { title: '设置' } },
    ],
  },
  { path: '/:pathMatch(.*)*', name: 'NotFound', redirect: '/home' },
]
