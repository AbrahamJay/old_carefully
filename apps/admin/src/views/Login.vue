<template>
  <div class="login-page">
    <div class="login-visual">
      <div class="visual-orb a"></div>
      <div class="visual-orb b"></div>
      <div class="brand">
        <div class="brand-mark">养</div>
        <div class="brand-name">社区养老管家</div>
      </div>
      <h1>让社区里的长辈，<br />被好好照顾。</h1>
      <p class="lead">陪诊、保洁、适老化、代办——<br />一个管家，把服务安排明白。</p>
      <div class="visual-tags">
        <span>确认</span><span>派单</span><span>留痕</span><span>收款</span>
      </div>
      <div class="visual-meta">示范街道 · 演示后台 v1.0</div>
    </div>

    <div class="login-panel">
      <div class="login-card">
        <div class="eyebrow">ADMIN CONSOLE</div>
        <h2>登录管理后台</h2>
        <p class="sub">确认订单、派单、标记收款、查看服务记录</p>
        <p class="role-hint">管理后台仅限管理员；家属、员工请在小程序端登录。</p>

        <el-form @submit.prevent="submit">
          <el-form-item label="账号">
            <el-input v-model="username" placeholder="管理员手机号" size="large" />
          </el-form-item>
          <el-form-item label="密码">
            <el-input v-model="password" type="password" show-password placeholder="密码" size="large" />
          </el-form-item>
          <el-button type="primary" size="large" class="submit" :loading="loading" @click="submit">
            登录
          </el-button>
        </el-form>

        <p class="demo">演示账号：13900000000 / Admin123!</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { login } from '../api'

const router = useRouter()
const username = ref('13900000000')
const password = ref('Admin123!')
const loading = ref(false)

async function submit() {
  if (!username.value || !password.value) {
    ElMessage.warning('请输入账号和密码')
    return
  }
  loading.value = true
  try {
    await login(username.value, password.value)
    router.push('/')
  } catch (e: any) {
    ElMessage.error(e.message || '登录失败')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  display: grid;
  grid-template-columns: 1.05fr 1fr;
  background: #F7F6F2;
}
.login-visual {
  position: relative;
  overflow: hidden;
  margin: 18px;
  padding: 52px 56px 40px;
  border-radius: 40px;
  background: radial-gradient(circle at 82% 16%, #388C65 0%, #1E6143 50%, #123E2A 100%);
  color: #fff;
  display: flex;
  flex-direction: column;
  justify-content: center;
  box-shadow: 0 32px 70px -24px rgba(22, 74, 51, 0.5);
}
.visual-orb {
  position: absolute;
  border-radius: 50%;
}
.visual-orb.a {
  width: 520px;
  height: 520px;
  right: -220px;
  top: -180px;
  background: radial-gradient(circle, rgba(246, 227, 186, 0.2) 0%, rgba(246, 227, 186, 0) 70%);
}
.visual-orb.b {
  width: 320px;
  height: 320px;
  left: -100px;
  bottom: -140px;
  border: 1px solid rgba(255, 255, 255, 0.12);
}
.brand { position: relative; z-index: 1; display: flex; align-items: center; gap: 12px; }
.brand-mark {
  width: 48px;
  height: 48px;
  border-radius: 16px;
  background: linear-gradient(135deg, #FFF7E8 0%, #F6E3BA 100%);
  color: #164A33;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 21px;
  font-weight: 700;
}
.brand-name { font-size: 15px; font-weight: 600; letter-spacing: 0.5px; }
h1 {
  position: relative;
  z-index: 1;
  margin: 60px 0 0;
  font-size: 44px;
  line-height: 1.32;
  font-weight: 700;
  letter-spacing: 0.5px;
}
.lead {
  position: relative;
  z-index: 1;
  margin-top: 20px;
  color: rgba(255, 255, 255, 0.72);
  font-size: 15px;
  line-height: 1.9;
}
.visual-tags {
  position: relative;
  z-index: 1;
  display: flex;
  gap: 10px;
  margin-top: 26px;
}
.visual-tags span {
  padding: 7px 16px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.1);
  border: 1px solid rgba(255, 255, 255, 0.14);
  font-size: 12px;
  color: rgba(255, 255, 255, 0.78);
}
.visual-meta {
  position: relative;
  z-index: 1;
  margin-top: 52px;
  font-size: 11px;
  letter-spacing: 1.5px;
  color: rgba(255, 255, 255, 0.38);
}
.login-panel {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px;
}
.login-card {
  width: 390px;
  padding: 36px 34px;
  border-radius: 28px;
  background: #FFFFFF;
  box-shadow: 0 28px 64px -24px rgba(22, 74, 51, 0.16);
}
.eyebrow { font-size: 10px; letter-spacing: 2px; color: #8C9690; }
h2 { margin: 10px 0 0; font-size: 28px; line-height: 1.3; color: #1A2420; }
.sub { margin: 8px 0 10px; color: #8C9690; font-size: 13px; line-height: 1.7; }
.role-hint { margin: 0 0 22px; color: #C25E0A; font-size: 12px; line-height: 1.6; background: #FFF3DF; padding: 8px 12px; border-radius: 10px; }
.submit { width: 100%; margin-top: 6px; height: 46px; border-radius: 14px; }
.demo { text-align: center; color: #A0A8A3; font-size: 12px; margin-top: 20px; }
@media (max-width: 860px) {
  .login-page { grid-template-columns: 1fr; }
  .login-visual { display: none; }
}
</style>
