<template>
  <main class="login-page">
    <section class="login-canvas">
      <div class="blob blob-1"></div>
      <div class="blob blob-2"></div>
      <div class="blob blob-3"></div>

      <div class="brand-pill"><span class="brand-dot">养</span><span class="brand-text-light">社区安心照护</span></div>

      <div class="hero-copy">
        <div class="hero-line">让家里的长辈，</div>
        <div class="hero-line highlight">有人陪、有人管。</div>
      </div>

      <div class="hero-tags">
        <span class="hero-tag">安心陪诊</span>
        <span class="hero-tag">居家保洁</span>
        <span class="hero-tag">适老改造</span>
        <span class="hero-tag">日常代办</span>
      </div>
    </section>

    <section class="login-sheet">
      <div class="sheet-head">
        <h1 class="sheet-title">账号登录</h1>
        <p class="sheet-sub">选择身份后，使用手机号和密码登录</p>
      </div>

      <div class="quick-roles">
        <button class="role-pill" :class="{ active: role === 'customer' }" @click="selectRole('customer')">
          <span class="role-icon">家</span>
          <span class="grow"><b class="role-name">我是家属</b><small class="role-desc">预约服务 · 查看陪诊记录</small></span>
        </button>
        <button class="role-pill" :class="{ active: role === 'staff' }" @click="selectRole('staff')">
          <span class="role-icon staff">护</span>
          <span class="grow"><b class="role-name">我是服务人员</b><small class="role-desc">接单上门 · 拍照留痕</small></span>
        </button>
      </div>

      <div class="input-group">
        <div class="input-pill"><span class="input-prefix">手机号</span><input v-model="phone" class="pill-field" type="tel" maxlength="11" placeholder="输入手机号" /></div>
        <div class="input-pill mt16"><span class="input-prefix">密码</span><input v-model="password" class="pill-field" type="password" maxlength="32" autocomplete="current-password" placeholder="请输入密码" /></div>
      </div>

      <button class="btn btn-primary login-submit" :disabled="loading" @click="submit">{{ loading ? '登录中...' : '立即进入' }}</button>
      <p v-if="error" class="login-error">{{ error }}</p>
      <p class="login-foot">登录即代表同意《隐私政策与长辈照护授权》</p>
    </section>
  </main>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { login } from '../api/http'
import { setLogin } from '../stores/auth'
import { showToast } from '../stores/toast'
import { DEFAULT_CUSTOMER_PHONE, DEFAULT_PASSWORD, DEFAULT_STAFF_PHONE } from '../constants'

const router = useRouter()
type LoginRole = 'customer' | 'staff'

const phone = ref(DEFAULT_CUSTOMER_PHONE)
const role = ref<LoginRole>('customer')
const password = ref(DEFAULT_PASSWORD)
const loading = ref(false)
const error = ref('')

function selectRole(nextRole: LoginRole) {
  role.value = nextRole
  phone.value = nextRole === 'staff' ? DEFAULT_STAFF_PHONE : DEFAULT_CUSTOMER_PHONE
  password.value = DEFAULT_PASSWORD
  error.value = ''
}

async function submit() {
  if (!phone.value.trim()) {
    error.value = '请输入手机号'
    return
  }
  if (!password.value) {
    error.value = '请输入密码'
    return
  }
  loading.value = true
  error.value = ''
  try {
    const data = await login(phone.value.trim(), password.value)
    if (!['customer', 'staff'].includes(data.user.role)) {
      error.value = '该账号不能登录 H5，请使用管理后台'
      return
    }
    if (data.user.role !== role.value) {
      error.value = data.user.role === 'staff'
        ? '该账号是服务人员账号，请选择“我是服务人员”登录'
        : '该账号是家属账号，请选择“我是家属”登录'
      return
    }
    setLogin(data)
    showToast('欢迎回来')
    router.replace(data.user.role === 'staff' ? '/staff/orders' : '/')
  } catch (e: any) {
    error.value = e.message || '登录失败'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page { min-height: 100dvh; background: #F7F6F2; display: flex; flex-direction: column; }
.login-canvas { position: relative; overflow: hidden; padding: calc(11.2cqw + env(safe-area-inset-top)) 5.8667cqw 14.6667cqw; background: radial-gradient(circle at 85% 18%, #358762 0%, #1D5E41 48%, #123E2A 100%); color: #fff; border-radius: 0 0 9.6cqw 9.6cqw; }
.blob { position: absolute; border-radius: 50%; }
.blob-1 { width: 56cqw; height: 56cqw; right: -16cqw; top: -13.3333cqw; background: radial-gradient(circle, rgba(246,227,186,.22), transparent 70%); }
.blob-2 { width: 42.6667cqw; height: 42.6667cqw; left: -13.3333cqw; bottom: -10.6667cqw; background: radial-gradient(circle, rgba(104,204,156,.2), transparent 70%); }
.blob-3 { width: 29.3333cqw; height: 29.3333cqw; right: 8cqw; bottom: 5.3333cqw; border: .2667cqw solid rgba(255,255,255,.1); }
.brand-pill { position: relative; z-index: 1; display: inline-flex; align-items: center; gap: 1.8667cqw; padding: 1.3333cqw 3.4667cqw 1.3333cqw 1.6cqw; background: rgba(255,255,255,.12); border: .1333cqw solid rgba(255,255,255,.2); border-radius: 999px; }
.brand-dot { width: 6.4cqw; height: 6.4cqw; border-radius: 50%; background: #F6E3BA; color: #164A33; display: grid; place-items: center; font-size: 3.4667cqw; font-weight: 700; }
.brand-text-light { font-size: 3.2cqw; color: rgba(255,255,255,.9); letter-spacing: .1333cqw; }
.hero-copy { position: relative; z-index: 1; margin-top: 5.8667cqw; }
.hero-line { font-size: 7.2cqw; line-height: 1.3; font-weight: 700; letter-spacing: .1333cqw; }
.hero-line.highlight { color: #F6E3BA; }
.hero-tags { position: relative; z-index: 1; display: flex; flex-wrap: wrap; gap: 1.8667cqw; margin-top: 4.2667cqw; }
.hero-tag { padding: 1.0667cqw 2.9333cqw; border-radius: 999px; background: rgba(255,255,255,.1); color: rgba(255,255,255,.82); font-size: 3.0667cqw; }
.login-sheet { position: relative; z-index: 2; margin: -8.5333cqw 3.7333cqw 0; padding: 5.3333cqw 4.5333cqw 5.8667cqw; background: #fff; border-radius: 6.4cqw; box-shadow: 0 3.7333cqw 8.5333cqw -2.1333cqw rgba(22,74,51,.1); }
.sheet-title { margin: 0; font-size: 5.0667cqw; font-weight: 700; color: #1A2420; }
.sheet-sub { margin: .8cqw 0 0; font-size: 3.3333cqw; color: #8C9690; }
.quick-roles { margin-top: 3.7333cqw; display: flex; flex-direction: column; gap: 2.1333cqw; }
.role-pill { display: flex; align-items: center; gap: 2.6667cqw; padding: 2.9333cqw 3.2cqw; border-radius: 4.2667cqw; background: #F5F4F0; border: .2667cqw solid transparent; text-align: left; transition: all .2s ease; }
.role-pill.active { background: #EBF5F0; border-color: #277A55; box-shadow: 0 1.6cqw 3.7333cqw -1.3333cqw rgba(31,99,69,.18); }
.role-icon { width: 10.1333cqw; height: 10.1333cqw; border-radius: 3.4667cqw 4cqw 3.2cqw 4cqw; background: #1F6345; color: #fff; display: grid; place-items: center; font-size: 4cqw; font-weight: 700; flex-shrink: 0; }
.role-icon.staff { background: #E87A48; }
.role-name { display: block; font-size: 3.8667cqw; font-weight: 600; color: #1A2420; }
.role-desc { display: block; margin-top: .5333cqw; font-size: 3.0667cqw; color: #6E7872; }
.input-group { margin-top: 3.7333cqw; }
.input-pill { display: flex; align-items: center; height: 12.2667cqw; padding: 0 3.7333cqw; background: #F5F4F0; border-radius: 999px; }
.mt16 { margin-top: 2.1333cqw; }
.input-prefix { width: 14.6667cqw; flex-shrink: 0; font-size: 3.6cqw; font-weight: 500; color: #54615B; }
.pill-field { flex: 1; min-width: 0; border: none; outline: none; background: transparent; font-size: 4cqw; color: #1A2420; }
.login-submit { display: block; width: 100%; margin-top: 4.8cqw; height: 12.8cqw; border-radius: 999px; font-size: 4.2667cqw; }
.login-error { margin: 2.1333cqw 0 0; padding: 2.1333cqw 2.6667cqw; border-radius: 2.6667cqw; background: #FDECE9; color: #B23B32; font-size: 2.9333cqw; text-align: center; }
.login-foot { margin-top: 3.4667cqw; text-align: center; font-size: 2.9333cqw; color: #A0A8A3; }
@media (min-width: 560px) {
  .login-page { min-height: calc(100dvh - 32px); border-radius: 28px; overflow: hidden; }
}
</style>
