<script setup>
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import { useUserStore } from '@/stores/user'
import { ROLE, ROLE_LABEL } from '@/constants/enums'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()

const form = reactive({ account: '', password: '', role: ROLE.PATIENT })
const error = ref('')
const loading = ref(false)
const roleOptions = Object.entries(ROLE_LABEL).map(([value, label]) => ({ value, label }))

async function handleLogin() {
  error.value = ''
  if (!form.account.trim()) {
    error.value = '请输入帐号（手机号 / 身份证号）'
    return
  }
  if (!form.password) {
    error.value = '请输入密码'
    return
  }

  loading.value = true
  try {
    await userStore.login({ ...form })
    ElMessage.success('登录成功，欢迎回来！')
    router.replace(route.query.redirect || { name: 'Home' })
  } catch (err) {
    error.value = err?.message || '登录失败，请稍后重试'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="auth-wrap">
    <section class="auth-side">
      <div class="side-inner">
        <span class="logo">🩺</span>
        <h1>智慧医疗AI辅助系统</h1>
        <p>AI 智能预诊分诊 · 精准挂号 · 报告解读 · 用药提醒</p>
        <ul class="side-list">
          <li>描述症状即可获得分诊建议</li>
          <li>检查报告专业术语一键转通俗语言</li>
          <li>服药计划自动推送，不再漏服</li>
        </ul>
      </div>
    </section>

    <section class="auth-main">
      <div class="auth-box">
        <h2>帐号登录</h2>

        <el-form label-position="top" @submit.prevent="handleLogin">
          <el-form-item label="帐号">
            <el-input
              v-model="form.account"
              placeholder="手机号 / 身份证号"
              size="large"
              clearable
            />
          </el-form-item>

          <el-form-item label="密码">
            <el-input
              v-model="form.password"
              type="password"
              placeholder="请输入密码"
              size="large"
              show-password
              @keyup.enter="handleLogin"
            />
          </el-form-item>

          <el-form-item label="角色">
            <el-radio-group v-model="form.role">
              <el-radio v-for="item in roleOptions" :key="item.value" :value="item.value">
                {{ item.label }}
              </el-radio>
            </el-radio-group>
          </el-form-item>

          <p v-if="error" class="err-msg">{{ error }}</p>

          <el-button
            class="btn-main"
            type="primary"
            size="large"
            :loading="loading"
            @click="handleLogin"
          >
            登录
          </el-button>
        </el-form>

        <div class="link-row">
          还没有账号？
          <router-link :to="{ name: 'Register' }">立即注册</router-link>
        </div>

        <p class="auth-tip">急危重症请直接拨打 120 或前往急诊科，AI 建议不替代专业诊断。</p>
      </div>
    </section>
  </div>
</template>

<style scoped lang="less">
.auth-wrap {
  flex: 1;
  display: flex;
  min-height: 100%;
}

.auth-side {
  flex: 1;
  display: flex;
  align-items: center;
  padding: 48px;
  background: linear-gradient(135deg, var(--primary), #2ec9b4);
  color: #fff;
}

.side-inner {
  max-width: 420px;

  .logo {
    font-size: 48px;
  }

  h1 {
    margin: 16px 0 12px;
    font-size: 30px;
  }

  p {
    opacity: 0.9;
    line-height: 1.8;
  }
}

.side-list {
  margin-top: 24px;
  padding-left: 20px;
  line-height: 2.2;
  opacity: 0.95;
}

.auth-main {
  flex: 0 0 460px;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 32px;
}

.auth-box {
  width: 100%;
  max-width: 360px;
  padding: 32px;
  .card();

  h2 {
    margin-bottom: 24px;
    font-size: 22px;
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

.auth-tip {
  margin-top: 20px;
  font-size: 12px;
  line-height: 1.7;
  color: var(--text-3);
}

.mq-lg({
  .auth-side { display: none; }
  .auth-main { flex: 1; }
});
</style>
