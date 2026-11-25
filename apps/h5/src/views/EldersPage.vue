<template>
  <main class="page no-tab">
    <header class="topbar">
      <button class="back" @click="router.push('/')">‹</button>
      <span class="topbar-title">我的长辈</span>
      <span class="topbar-space"></span>
    </header>

    <div class="row between head-block">
      <div>
        <span class="eyebrow">FAMILY</span>
        <h1>我的长辈</h1>
        <p>共 {{ elders.length }} 位</p>
      </div>
      <div class="head-buttons">
        <button class="btn btn-ghost mini-btn" @click="router.push('/elders/bind')">绑定已有长辈</button>
        <button class="btn btn-primary mini-btn" @click="router.push('/elders/new')">新增长辈</button>
      </div>
    </div>

    <div v-if="!elders.length && !loading" class="card empty">
      <div class="empty-mark">家</div>
      <div class="empty-title">还没有长辈档案</div>
      <div class="empty-desc">先建立一份档案，下单时就能直接选择。</div>
      <button class="btn btn-primary" @click="router.push('/elders/new')">新增长辈</button>
    </div>

    <article v-for="elder in elders" :key="elder.id" class="elder-card" @click="router.push(`/elders/${elder.id}/edit`)">
      <div class="row between">
        <div class="row">
          <span class="avatar">{{ elder.name.slice(0, 1) }}</span>
          <div class="elder-info"><strong>{{ elder.name }}</strong><small>{{ elder.community || '未填社区' }} · {{ elder.address || '未填地址' }}</small></div>
        </div>
        <span class="chevron">›</span>
      </div>
      <div class="divider"></div>
      <div class="small muted">紧急联系人：{{ elder.emergency_name || '未填' }} {{ elder.emergency_phone }}</div>
      <div v-if="elder.health_notes" class="small muted mt8">备注：{{ elder.health_notes }}</div>
      <div v-if="elder.invite_code" class="invite-line">
        <span>邀请码</span><b>{{ elder.invite_code }}</b><button class="copy" @click.stop="copyCode(elder.invite_code)">复制</button>
      </div>
    </article>
  </main>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { get } from '../api/http'
import { showToast } from '../stores/toast'

const router = useRouter()
const elders = ref<any[]>([])
const loading = ref(true)

async function load() {
  loading.value = true
  try { elders.value = await get<any[]>('/elders') } finally { loading.value = false }
}

async function copyCode(code: string) {
  try {
    await navigator.clipboard.writeText(code)
    showToast('邀请码已复制')
  } catch {
    showToast('复制失败，请长按选择')
  }
}

onMounted(load)
</script>

<style scoped>
.head-block { align-items: flex-end; margin: 6px 2px 16px; }
.head-block h1 { margin: 6px 0 0; font-size: 28px; }
.head-block p { margin: 4px 0 0; font-size: 11px; color: var(--muted); }
.head-buttons { display: flex; gap: 6px; flex-wrap: wrap; justify-content: flex-end; }
.mini-btn { padding: 9px 12px; font-size: 11px; }
.elder-card { background: #fff; border-radius: 24px 20px 26px 20px; padding: 16px; margin-bottom: 10px; box-shadow: var(--shadow); }
.elder-card:active { opacity: .82; }
.elder-info { margin-left: 10px; }
.elder-info strong { display: block; font-size: 15px; }
.elder-info small { display: block; margin-top: 3px; font-size: 10px; color: var(--muted); }
.invite-line { display: flex; align-items: center; gap: 8px; margin-top: 12px; padding-top: 10px; border-top: 1px solid var(--line); font-size: 10px; color: var(--muted); }
.invite-line b { padding: 3px 9px; border-radius: 999px; background: var(--soft); color: var(--primary); font-size: 10px; letter-spacing: 1px; }
.invite-line .copy { margin-left: auto; border: none; background: transparent; color: var(--primary); font-size: 10px; font-weight: 700; }
</style>
