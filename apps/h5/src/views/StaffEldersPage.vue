<template>
  <main class="page no-tab">
    <header class="topbar">
      <button class="back" @click="router.push('/staff/profile')">‹</button>
      <span class="topbar-title">我的服务对象</span>
      <span class="topbar-space"></span>
    </header>

    <div class="page-intro">
      <span class="eyebrow">SERVICE OBJECTS</span>
      <h1>我的服务对象</h1>
      <p>共 {{ elders.length }} 位</p>
    </div>

    <div v-if="loading" class="card">
      <div class="skeleton" style="height: 22px; width: 45%"></div>
      <div class="skeleton mt12" style="height: 12px; width: 75%"></div>
    </div>

    <div v-else-if="!elders.length" class="card organic empty">
      <div class="empty-mark">单</div>
      <div class="empty-title">暂时没有服务对象</div>
      <div class="empty-desc">管家派单后，服务地址、联系人和照护备注会出现在这里。</div>
    </div>

    <article v-for="elder in elders" :key="elder.id" class="elder-card" @click="selected = elder">
      <div class="row between">
        <div class="row">
          <span class="avatar">{{ elder.name.slice(0, 1) }}</span>
          <div class="elder-info">
            <strong>{{ elder.name }}</strong>
            <small>{{ elder.community || '未填社区' }} · {{ elder.address || '未填地址' }}</small>
          </div>
        </div>
        <span class="chevron">›</span>
      </div>
      <div class="divider"></div>
      <div class="small muted">联系人：{{ elder.emergency_name || '未填' }} {{ elder.emergency_phone }}</div>
      <div class="small muted mt8">长辈电话：{{ elder.phone || '未填' }}</div>
      <div v-if="elder.health_notes" class="small muted mt8">备注：{{ elder.health_notes }}</div>
    </article>

    <div v-if="selected" class="sheet-mask" @click.self="selected = null">
      <section class="sheet">
        <div class="row between">
          <div><span class="eyebrow">SERVICE OBJECT</span><h2>{{ selected.name }}</h2></div>
          <button class="sheet-close" @click="selected = null">×</button>
        </div>
        <div class="info-row"><span>服务地址</span><b>{{ selected.address || '未填' }}</b></div>
        <div class="info-row"><span>联系电话</span><b>{{ selected.phone || selected.emergency_phone || '未填' }}</b></div>
        <div class="info-row"><span>紧急联系人</span><b>{{ selected.emergency_name || '未填' }} {{ selected.emergency_phone }}</b></div>
        <div class="info-block"><span>照护备注</span><p>{{ selected.health_notes || '无' }}</p></div>
        <button class="btn btn-primary btn-block mt16" @click="selected = null">知道了</button>
      </section>
    </div>
  </main>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { get } from '../api/http'
import { showToast } from '../stores/toast'

const router = useRouter()
const elders = ref<any[]>([])
const selected = ref<any>(null)
const loading = ref(true)

async function load() {
  loading.value = true
  try {
    elders.value = await get<any[]>('/elders')
  } catch (e: any) {
    showToast(e.message || '加载失败')
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.page-intro { margin: 0 2px 14px; }
.page-intro h1 { margin: 6px 0 0; font-size: 26px; }
.page-intro p { margin: 4px 0 0; font-size: 10px; color: var(--muted); }
.elder-card { background: #fff; border-radius: 24px 20px 26px 20px; padding: 16px; margin-bottom: 10px; box-shadow: var(--shadow); }
.elder-card:active { opacity: .82; }
.avatar { width: 38px; height: 38px; border-radius: 14px 16px 12px 16px; display: grid; place-items: center; background: var(--soft); color: var(--primary); font-size: 14px; font-weight: 700; flex-shrink: 0; }
.elder-info { margin-left: 10px; }
.elder-info strong { display: block; font-size: 15px; }
.elder-info small { display: block; margin-top: 3px; font-size: 10px; color: var(--muted); }
.skeleton { border-radius: 999px; background: linear-gradient(90deg, #F2F1EC, #FAF9F5, #F2F1EC); }
.sheet-mask { position: fixed; inset: 0; z-index: 60; display: flex; align-items: flex-end; background: rgba(18, 34, 27, .38); }
.sheet { width: 100%; max-height: 82vh; overflow-y: auto; padding: 22px 20px calc(20px + env(safe-area-inset-bottom)); border-radius: 28px 28px 0 0; background: #fff; box-shadow: 0 -20px 50px -18px rgba(22,74,51,.25); }
.sheet h2 { margin: 6px 0 16px; font-size: 24px; }
.sheet-close { width: 34px; height: 34px; border: none; border-radius: 12px; background: #F2F1EC; color: var(--muted); font-size: 20px; line-height: 1; }
.info-row { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; padding: 6px 0; font-size: 12px; }
.info-row span { color: var(--muted); flex-shrink: 0; }
.info-row b { text-align: right; font-weight: 600; }
.info-block { margin-top: 12px; padding-top: 12px; border-top: 1px solid var(--line); font-size: 12px; }
.info-block span { color: var(--muted); }
.info-block p { margin: 6px 0 0; line-height: 1.8; color: var(--sub); }
</style>
