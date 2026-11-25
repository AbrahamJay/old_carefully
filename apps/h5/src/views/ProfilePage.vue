<template>
  <main class="page">
    <section class="profile-hero">
      <div class="profile-top">
        <span class="profile-avatar">{{ avatarText }}</span>
        <div class="grow">
          <strong>{{ auth.user?.name || '未登录' }}</strong>
          <small>{{ auth.user?.phone || '' }} · 家属</small>
        </div>
        <span class="role-pill">家属</span>
      </div>
      <div class="profile-stats">
        <button class="stat" @click="router.push('/elders')"><b>{{ elderCount }}</b><span>我的长辈</span></button>
        <button class="stat" @click="callSteward"><b>管家</b><span>一键联系</span></button>
        <button class="stat" @click="router.push('/emergency')"><b>120</b><span>紧急联系</span></button>
      </div>
    </section>

    <section class="card organic menu-card">
      <button class="menu-item" @click="router.push('/elders')"><span class="menu-icon">家</span><span class="grow"><b>我的长辈</b><small>档案、健康备注与邀请码</small></span><span class="chevron">›</span></button>
      <button class="menu-item" @click="router.push('/orders')"><span class="menu-icon warm">单</span><span class="grow"><b>我的订单</b><small>预约、支付、服务记录与退款</small></span><span class="chevron">›</span></button>
      <button class="menu-item" @click="router.push('/emergency')"><span class="menu-icon red">急</span><span class="grow"><b>紧急联系</b><small>120 / 社区 / 管家</small></span><span class="chevron">›</span></button>
      <button class="menu-item" @click="router.push('/privacy')"><span class="menu-icon">隐</span><span class="grow"><b>隐私政策与授权</b><small>数据如何被使用</small></span><span class="chevron">›</span></button>
      <button class="menu-item" @click="callSteward"><span class="menu-icon warm">电</span><span class="grow"><b>联系社区管家</b><small>{{ SERVICE_PHONE }}</small></span><span class="chevron">›</span></button>
    </section>

    <section class="card warm">
      <h2 class="section-title">演示环境</h2>
      <p class="small muted mt8">个人小程序主体不支持微信支付；当前支付/退款均为模拟或线下标记。</p>
      <p class="small muted mt8">家属账号：13800000001 / 123456</p>
    </section>

    <button class="btn btn-ghost btn-block logout" @click="logout">退出登录</button>
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { get } from '../api/http'
import { auth, clearAuth } from '../stores/auth'
import { SERVICE_PHONE } from '../constants'

const router = useRouter()
const elderCount = ref(0)
const avatarText = computed(() => auth.user?.name?.slice(0, 1) || '家')

async function load() {
  try {
    const elders = await get<any[]>('/elders')
    elderCount.value = elders.length
  } catch { /* handled by http */ }
}

function callSteward() {
  location.href = 'tel:' + SERVICE_PHONE
}

function logout() {
  clearAuth()
  router.replace('/login')
}

onMounted(load)
</script>

<style scoped>
.profile-hero { position: relative; overflow: hidden; border-radius: 30px 24px 32px 24px; padding: 22px 20px 18px; background: radial-gradient(circle at 88% 12%, #388C65 0%, #1E6143 52%, #13402B 100%); color: #fff; box-shadow: 0 22px 46px -18px rgba(22,74,51,.38); margin-bottom: 12px; }
.profile-top { display: flex; align-items: center; gap: 11px; }
.profile-avatar { width: 50px; height: 50px; border-radius: 18px 20px 16px 20px; display: grid; place-items: center; background: linear-gradient(135deg, #FFF7E8, #F6E3BA); color: var(--deep); font-weight: 700; font-size: 20px; }
.profile-top strong { display: block; font-size: 22px; }
.profile-top small { display: block; margin-top: 3px; font-size: 10px; color: rgba(255,255,255,.62); }
.role-pill { padding: 5px 10px; border-radius: 999px; background: rgba(255,255,255,.13); color: var(--gold); font-size: 9px; }
.profile-stats { display: flex; margin-top: 20px; padding-top: 14px; border-top: 1px solid rgba(255,255,255,.14); }
.stat { flex: 1; border: none; background: transparent; color: #fff; text-align: center; }
.stat b { display: block; font-size: 17px; color: var(--gold); }
.stat span { display: block; margin-top: 3px; font-size: 9px; color: rgba(255,255,255,.52); }
.menu-card { padding: 5px 16px; }
.menu-item { width: 100%; display: flex; align-items: center; gap: 11px; padding: 14px 0; border: none; border-bottom: 1px solid var(--line); background: transparent; text-align: left; }
.menu-item:last-child { border-bottom: none; }
.menu-icon { width: 36px; height: 36px; border-radius: 13px; display: grid; place-items: center; background: var(--soft); color: var(--primary); font-size: 12px; font-weight: 700; flex-shrink: 0; }
.menu-icon.warm { background: var(--peach); color: #D96B38; }
.menu-icon.red { background: #FDECE9; color: #C93B2B; }
.menu-item b { display: block; font-size: 13px; }
.menu-item small { display: block; margin-top: 2px; font-size: 10px; color: var(--muted); }
.logout { margin-top: 4px; }
</style>
