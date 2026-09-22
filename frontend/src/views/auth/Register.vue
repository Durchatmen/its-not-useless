<script setup>
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import * as authApi from '@/api/auth'

const router = useRouter()

// 注册环节不校验短信验证码，只做实名核验
const form = reactive({ phone: '', password: '', password2: '', name: '', idcard: '' })
const error = ref('')
const loading = ref(false)

function validate() {
  if (!/^1\d{10}$/.test(form.phone)) return '请输入正确的 11 位手机号'
  if (form.password.length < 6) return '密码至少 6 位'
  if (form.password !== form.password2) return '两次输入的密码不一致'
  if (!form.name.trim()) return '请输入真实姓名'
  if (!/^\d{17}[\dXx]$/.test(form.idcard)) return '请输入正确的 18 位身份证号'
  return ''
}

async function handleRegister() {
  error.value = validate()
  if (error.value) return

  loading.value = true
  try {
    await authApi.register({
      phone: form.phone,
      password: form.password,
      name: form.name,
      idcard: form.idcard,
    })
    ElMessage.success('注册成功，请登录')
    router.replace({ name: 'Login' })
  } catch (err) {
    error.value = err?.message || '注册失败，请稍后重试'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="auth-wrap">
    <div class="auth-box">
      <h2>注册账号</h2>
      <p class="sub">实名认证后可绑定就诊卡，为家人代挂号</p>

      <el-form label-position="top" @submit.prevent="handleRegister">
        <el-form-item label="手机号">
          <el-input v-model="form.phone" maxlength="11" placeholder="请输入 11 位手机号" clearable />
        </el-form-item>

        <el-form-item label="密码">
          <el-input v-model="form.password" type="password" show-password placeholder="至少 6 位" />
        </el-form-item>

        <el-form-item label="确认密码">
          <el-input v-model="form.password2" type="password" show-password placeholder="再次输入密码" />
        </el-form-item>

        <el-form-item label="真实姓名">
          <el-input v-model="form.name" placeholder="用于实名认证" />
        </el-form-item>

        <el-form-item label="身份证号">
          <el-input v-model="form.idcard" maxlength="18" placeholder="18 位身份证号" />
        </el-form-item>

        <p v-if="error" class="err-msg">{{ error }}</p>

        <el-button class="btn-main" type="primary" size="large" :loading="loading" @click="handleRegister">
          注册
        </el-button>
      </el-form>

      <div class="link-row">
        已有账号？
        <router-link :to="{ name: 'Login' }">返回登录</router-link>
      </div>
    </div>
  </div>
</template>

<style scoped lang="less">
.auth-wrap {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px 16px;
}

.auth-box {
  width: 100%;
  max-width: 420px;
  padding: 32px;
  .card();

  h2 {
    font-size: 22px;
  }

  .sub {
    margin: 8px 0 24px;
    font-size: 13px;
    color: var(--text-2);
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

.link-row {
  margin-top: 16px;
  text-align: center;
  font-size: 13px;
  color: var(--text-2);
}
</style>
