<template>
  <main class="page no-tab">
    <header class="topbar">
      <span class="topbar-space"></span>
      <span class="topbar-title">我的</span>
      <span class="topbar-space"></span>
    </header>

    <section class="staff-profile-card">
      <span class="staff-avatar">{{ avatarText }}</span>
      <div class="staff-profile-main"><h1>{{ auth.user?.name }}</h1><p>{{ auth.user?.phone }} · 服务人员</p><small>{{ auth.user?.station_name || '未分配区域' }}</small></div>
      <span class="role-pill">员工</span>
    </section>

    <section class="card organic menu-card">
      <button class="menu-item" @click="router.push('/staff/elders')">
        <span class="menu-icon">务</span>
        <span class="grow"><b>我的服务对象</b><small>已派单的服务地址与照护备注</small></span>
        <span class="chevron">›</span>
      </button>
      <button class="menu-item" @click="callService">
        <span class="menu-icon">电</span>
        <span class="grow"><b>联系社区管家</b><small>{{ SERVICE_PHONE }}</small></span>
        <span class="chevron">›</span>
      </button>
      <button class="menu-item" @click="router.push('/privacy')">
        <span class="menu-icon">隐</span>
        <span class="grow"><b>隐私政策与授权</b><small>服务数据如何被使用</small></span>
        <span class="chevron">›</span>
      </button>
    </section>

    <p class="account-note">账号由社区管家统一开通；如需调整服务区域或停用账号，请联系管家。</p>
    <button class="btn btn-ghost btn-block" @click="logout">退出登录</button>
  </main>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { auth, clearAuth } from '../stores/auth'
import { SERVICE_PHONE } from '../constants'

const router = useRouter()
const avatarText = computed(() => auth.user?.name?.slice(0, 1) || '员')

function callService() {
  location.href = 'tel:' + SERVICE_PHONE
}

function logout() {
  if (!confirm('确认退出当前账号？')) return
  clearAuth()
  router.replace('/login')
}
</script>

<style scoped>
.staff-profile-card { display: flex; align-items: center; gap: 13px; border-radius: 28px 22px 30px 22px; padding: 24px 20px; background: radial-gradient(circle at 88% 12%, #388C65 0%, #1E6143 52%, #13402B 100%); color: #fff; box-shadow: 0 20px 44px -18px rgba(22,74,51,.4); }
.staff-avatar { width: 54px; height: 54px; border-radius: 19px 21px 17px 21px; display: grid; place-items: center; background: linear-gradient(135deg,#FFF7E8,#F6E3BA); color: var(--deep); font-size: 21px; font-weight: 700; }
.staff-profile-card h1 { margin: 0; font-size: 23px; }
.staff-profile-card p { margin: 4px 0 0; font-size: 10px; color: rgba(255,255,255,.7); }
.staff-profile-card small { display: block; margin-top: 4px; font-size: 9px; color: var(--gold); }
.staff-profile-main { min-width: 0; flex: 1; }
.role-pill { padding: 5px 11px; border-radius: 999px; background: rgba(255,255,255,.14); border: 1px solid rgba(255,255,255,.2); color: var(--gold); font-size: 10px; flex-shrink: 0; }
.menu-card { margin-top: 14px; padding: 5px 16px; }
.menu-item { width: 100%; display: flex; align-items: center; gap: 11px; padding: 14px 0; border: none; border-bottom: 1px solid var(--line); background: transparent; text-align: left; }
.menu-item:last-child { border-bottom: none; }
.menu-icon { width: 36px; height: 36px; border-radius: 13px; display: grid; place-items: center; background: var(--soft); color: var(--primary); font-size: 12px; font-weight: 700; }
.menu-item b { display: block; font-size: 13px; }
.menu-item small { display: block; margin-top: 2px; font-size: 10px; color: var(--muted); }
.account-note { margin: 16px 4px; font-size: 10px; line-height: 1.7; color: var(--muted); }
</style>
