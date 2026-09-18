<script setup>
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import { useAdminUserStore } from '@/stores/user'

const route = useRoute()
const router = useRouter()
const userStore = useAdminUserStore()

const form = reactive({ account: '', password: '' })
const error = ref('')
const loading = ref(false)

async function handleLogin() {
  error.value = ''
  if (!form.account.trim()) {
    error.value = '请输入管理员账号'
    return
  }
  if (!form.password) {
    error.value = '请输入密码'
    return
  }

  loading.value = true
  try {
    await userStore.login({ ...form })
    ElMessage.success('登录成功')
    router.replace(route.query.redirect || { name: 'Dashboard' })
  } catch (err) {
    error.value = err?.message || '登录失败，请稍后重试'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login-page">
    <div class="login-box">
      <div class="head">
        <span class="logo">🩺</span>
        <h2>智慧医疗AI辅助系统</h2>
        <p>管理 / 运营后台</p>
      </div>

      <el-form label-position="top" @submit.prevent="handleLogin">
        <el-form-item label="管理员账号">
          <el-input v-model="form.account" size="large" placeholder="请输入账号" clearable />
        </el-form-item>

        <el-form-item label="密码">
          <el-input
            v-model="form.password"
            type="password"
            size="large"
            show-password
            placeholder="请输入密码"
            @keyup.enter="handleLogin"
          />
        </el-form-item>

        <p v-if="error" class="err-msg">{{ error }}</p>

        <el-button class="btn-main" type="primary" size="large" :loading="loading" @click="handleLogin">
          登录
        </el-button>
      </el-form>

      <el-alert
        class="tip"
        type="info"
        :closable="false"
        show-icon
        title="后台管理端建议内网 / VPN 访问，独立鉴权（需求分析 9.3）。"
      />
    </div>
  </div>
</template>

<style scoped lang="less">
.login-page {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 32px 16px;
}

.login-box {
  width: 100%;
  max-width: 380px;
  padding: 32px;
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow);
}

.head {
  text-align: center;
  margin-bottom: 24px;

  .logo {
    font-size: 40px;
  }

  h2 {
    margin: 8px 0 4px;
    font-size: 20px;
  }

  p {
    font-size: 13px;
    color: var(--text-3);
  }
}

.btn-main {
  width: 100%;
}

.err-msg {
  margin-bottom: 12px;
  color: var(--red);
  font-size: 13px;
}

.tip {
  margin-top: 20px;
}
</style>
