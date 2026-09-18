<script setup>
import { useRouter } from 'vue-router'

import { TRIAGE_ACTION } from '@/constants/enums'

const props = defineProps({
  /** 分诊卡片回传的 buttonAction，如 GO_REGISTER */
  action: { type: String, default: '' },
  /** 推荐科室，跳转挂号时带上 */
  department: { type: String, default: '' },
  disabled: { type: Boolean, default: false },
})

const router = useRouter()

function handleClick() {
  if (props.action !== TRIAGE_ACTION.GO_REGISTER) return
  router.push({ name: 'DeptSelect', query: { department: props.department } })
}
</script>

<template>
  <el-button
    v-if="action === TRIAGE_ACTION.GO_REGISTER"
    type="primary"
    :disabled="disabled"
    @click="handleClick"
  >
    去挂号
  </el-button>
</template>
