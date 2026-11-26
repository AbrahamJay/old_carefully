<template>
  <div class="layout">
    <aside class="aside">
      <div class="brand">
        <div class="brand-mark">养</div>
        <div>
          <div class="brand-title">社区养老管家</div>
          <div class="brand-sub">示范街道</div>
        </div>
      </div>

      <div class="menu-label">工作台</div>
      <el-menu :default-active="route.path" router class="menu">
        <el-menu-item index="/">今日概览</el-menu-item>
        <el-menu-item index="/dispatch">
          <span>派单工作台</span>
          <span v-if="pendingBadge" class="menu-badge">{{ pendingBadge }}</span>
        </el-menu-item>
        <el-menu-item index="/anomalies">
          <span>异常巡检</span>
          <span v-if="anomalyBadge" class="menu-badge">{{ anomalyBadge }}</span>
        </el-menu-item>
        <el-menu-item index="/orders">服务订单</el-menu-item>
        <el-menu-item index="/elders">长辈档案</el-menu-item>
        <el-menu-item index="/services">服务项目</el-menu-item>
        <el-menu-item index="/staff">服务人员</el-menu-item>
        <el-menu-item index="/stations">区域管理</el-menu-item>
        <el-menu-item index="/suppliers">合作供给</el-menu-item>
        <el-menu-item index="/reviews">服务评价</el-menu-item>
      </el-menu>

      <div class="aside-foot">
        <div class="foot-title">个人小程序演示版</div>
        <div class="foot-sub">不支持微信支付 · 线下收款</div>
      </div>
    </aside>

    <div class="content">
      <header class="header">
        <div>
          <div class="header-title">管理后台</div>
          <div class="header-sub">确认、派单、收款和服务留痕</div>
        </div>
        <div class="header-right">
          <div class="header-user">{{ user?.name || '管理员' }}</div>
          <el-button link type="primary" @click="handleLogout">退出</el-button>
        </div>
      </header>
      <main class="main">
        <router-view />
      </main>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { getUser, logout, request } from '../api'

const route = useRoute()
const user = getUser()
const pendingBadge = ref(0)
const anomalyBadge = ref(0)
let timer: number | undefined

async function loadBadges() {
  // 两块角标独立失败：任一接口异常不影响另一个
  try {
    const data = await request('/admin/dispatch/summary')
    pendingBadge.value = Number(data.pending_confirm || 0) + Number(data.confirmed || 0)
  } catch {
    // 角标失败不影响页面；登录过期由 request 统一处理
  }
  try {
    const data = await request('/admin/tasks/summary')
    anomalyBadge.value = Number(data.open || 0)
  } catch {
    // 异常巡检关闭或接口失败时保持不显示
  }
}

function handleRefresh() {
  loadBadges()
}

onMounted(() => {
  loadBadges()
  // 工作台/异常页操作后主动刷新角标；另外每 60 秒兜底同步一次
  window.addEventListener('dispatch:refresh', handleRefresh)
  window.addEventListener('anomaly:refresh', handleRefresh)
  timer = window.setInterval(loadBadges, 60000)
})

onUnmounted(() => {
  window.removeEventListener('dispatch:refresh', handleRefresh)
  window.removeEventListener('anomaly:refresh', handleRefresh)
  if (timer) window.clearInterval(timer)
})

function handleLogout() {
  logout()
}
</script>

<style scoped>
.layout {
  min-height: 100vh;
  display: flex;
  gap: 18px;
  padding: 18px;
  background: #F7F6F2;
}
.aside {
  width: 220px;
  flex-shrink: 0;
  height: calc(100vh - 36px);
  position: sticky;
  top: 18px;
  display: flex;
  flex-direction: column;
  padding: 20px 14px;
  border-radius: 28px;
  background: linear-gradient(160deg, #123E2A 0%, #164A33 55%, #1F6345 100%);
  color: #FFFFFF;
  box-shadow: 0 28px 60px -24px rgba(22, 74, 51, 0.45);
  overflow: hidden;
}
.aside::before {
  content: "";
  position: absolute;
  width: 280px;
  height: 280px;
  right: -140px;
  top: -120px;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(246, 227, 186, 0.18) 0%, rgba(246, 227, 186, 0) 70%);
}
.brand { position: relative; z-index: 1; display: flex; align-items: center; gap: 10px; padding: 4px 8px 24px; }
.brand-mark {
  width: 42px;
  height: 42px;
  border-radius: 14px;
  background: linear-gradient(135deg, #FFF7E8 0%, #F6E3BA 100%);
  color: #164A33;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 19px;
  font-weight: 700;
  flex-shrink: 0;
}
.brand-title { font-size: 15px; font-weight: 700; letter-spacing: 0.5px; }
.brand-sub { font-size: 11px; color: rgba(255, 255, 255, 0.5); margin-top: 3px; }
.menu-label {
  position: relative;
  z-index: 1;
  font-size: 10px;
  letter-spacing: 2px;
  color: rgba(255, 255, 255, 0.35);
  padding: 0 12px 8px;
}
.menu { position: relative; z-index: 1; border-right: none; background: transparent; }
.menu :deep(.el-menu-item) {
  color: rgba(255, 255, 255, 0.72);
  height: 46px;
  line-height: 46px;
  border-radius: 16px;
  margin-bottom: 5px;
  font-size: 13px;
}
.menu :deep(.el-menu-item:hover) { background: rgba(255, 255, 255, 0.08); color: #fff; }
.menu :deep(.el-menu-item.is-active) {
  background: rgba(246, 227, 186, 0.16);
  color: #F6E3BA;
  font-weight: 600;
}
.menu-badge {
  margin-left: auto;
  min-width: 20px;
  padding: 0 7px;
  border-radius: 999px;
  background: rgba(246, 227, 186, 0.22);
  color: #F6E3BA;
  font-size: 11px;
  line-height: 20px;
  text-align: center;
}
.aside-foot {
  position: relative;
  z-index: 1;
  margin-top: auto;
  padding: 16px 10px 4px;
  border-top: 1px solid rgba(255, 255, 255, 0.1);
}
.foot-title { font-size: 11px; color: rgba(255, 255, 255, 0.55); }
.foot-sub { font-size: 10px; color: rgba(255, 255, 255, 0.3); margin-top: 3px; }

.content {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}
.header {
  height: 70px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 8px 0 6px;
}
.header-title { font-size: 18px; font-weight: 700; color: #1A2420; }
.header-sub { font-size: 12px; color: #8C9690; margin-top: 3px; }
.header-right { display: flex; align-items: center; gap: 14px; }
.header-user { font-size: 13px; color: #54615B; }
.main { flex: 1; padding: 6px 2px 24px; }
</style>
