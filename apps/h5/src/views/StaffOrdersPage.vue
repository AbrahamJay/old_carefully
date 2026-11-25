<template>
  <main class="page staff-page">
    <header class="topbar">
      <span class="topbar-space"></span>
      <span class="topbar-title">工作台</span>
      <span class="topbar-space"></span>
    </header>
    <section class="staff-shell">
      <div class="staff-aura a"></div>
      <div class="staff-aura b"></div>
      <div class="row between shell-top">
        <div class="grow">
          <span class="eyebrow light">STAFF DESK</span>
          <h1 class="staff-title">{{ auth.user?.name }}，共 {{ orders.length }} 单</h1>
          <p class="staff-sub">{{ auth.user?.station_name || '服务区域' }} · 今日 {{ todayCount }} 单 · 待处理 {{ pendingCount }} 单</p>
        </div>
        <button class="staff-avatar" @click="router.push('/staff/profile')">{{ avatarText }}</button>
      </div>
      <div class="shell-stats">
        <div class="shell-stat"><b>{{ todayCount }}</b><span>今日预约</span></div>
        <div class="shell-stat"><b>{{ pendingCount }}</b><span>待处理</span></div>
        <div class="shell-stat"><b>{{ completedCount }}</b><span>累计完成</span></div>
      </div>
    </section>

    <div class="order-filter">
      <button class="filter-chip" :class="{ active: filter === 'all' }" @click="setFilter('all')">全部 {{ orders.length }}</button>
      <button class="filter-chip" :class="{ active: filter === 'pending' }" @click="setFilter('pending')">待处理 {{ pendingCount }}</button>
      <button class="filter-chip" :class="{ active: filter === 'today' }" @click="setFilter('today')">今日 {{ todayCount }}</button>
    </div>

    <div v-if="!visibleOrders.length && !loading" class="card organic empty">
      <div class="empty-mark">等</div>
      <div class="empty-title">{{ orders.length ? '当前筛选下没有订单' : '暂时没有派给你的单' }}</div>
      <div class="empty-desc">{{ orders.length ? '切到「全部」可以查看历史订单。' : '管家确认并派单后，才会出现在这里。' }}</div>
      <button class="btn btn-ghost" @click="load">刷新看看</button>
    </div>

    <article v-for="order in visibleOrders" :key="order.id" class="order-bubble" @click="goRecord(order.id)">
      <div class="row between">
        <div class="row"><i class="order-dot"></i><strong class="order-service">{{ order.service_name }}</strong></div>
        <div class="row order-tags">
          <span v-if="order.paymentText" class="tag" :class="order.paymentCls">{{ order.paymentText }}</span>
          <span class="tag" :class="order.statusCls">{{ order.statusText }}</span>
        </div>
      </div>
      <div class="order-meta">{{ order.elder_name }} · 预约 {{ order.timeText }}</div>
      <div class="row between mt16">
        <span class="order-no">{{ order.order_no }}</span>
        <span class="amount">¥{{ order.amountText }} <span class="chevron">›</span></span>
      </div>
      <div class="order-hint">{{ order.status === 'completed' ? '点开查看服务记录' : '点开处理：接单 / 开始 / 记录 / 完成' }}</div>
    </article>
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { get } from '../api/http'
import { auth } from '../stores/auth'
import { dateTime, money, statusInfo } from '../api/format'
import { showToast } from '../stores/toast'

const router = useRouter()
const orders = ref<any[]>([])
const loading = ref(true)
const filter = ref('all')
const todayCount = ref(0)
const pendingCount = ref(0)
const completedCount = ref(0)
const avatarText = computed(() => auth.user?.name?.slice(0, 1) || '员')

function dateKey(value: string) {
  const d = new Date(value)
  if (isNaN(d.getTime())) return ''
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

const visibleOrders = computed(() => {
  const today = dateKey(new Date().toISOString())
  return orders.value.filter(order => {
    if (filter.value === 'today') return dateKey(order.scheduled_at) === today
    if (filter.value === 'pending') return ['assigned', 'in_service'].includes(order.status)
    return true
  })
})

function setFilter(value: string) { filter.value = value }

async function load() {
  loading.value = true
  try {
    const data = await get<any>('/orders?page=1&page_size=50')
    const list = (data.items || []).map((item: any) => {
      const status = statusInfo(item.status)
      const remaining = Number(item.remaining_cents || 0)
      let paymentText = ''
      if (item.payment_status === 'refunded') paymentText = '已退款'
      else if (item.status === 'completed' && remaining > 0) paymentText = '尾款未结'
      else if (['assigned', 'in_service'].includes(item.status) && remaining > 0 && item.payment_status === 'unpaid') paymentText = '定金未付'
      return {
        ...item,
        statusText: item.status === 'assigned' ? '待接单' : item.status === 'completed' ? '服务已完成' : status.text,
        statusCls: status.cls,
        paymentText,
        paymentCls: paymentText === '已退款' ? 'tag-gray' : 'tag-inservice',
        amountText: money(item.amount_cents),
        timeText: dateTime(item.scheduled_at)
      }
    })
    const rank: Record<string, number> = { in_service: 0, assigned: 1, pending_confirm: 2, completed: 3, cancelled: 4 }
    list.sort((a: any, b: any) => {
      const pa = rank[a.status] ?? 9
      const pb = rank[b.status] ?? 9
      if (pa !== pb) return pa - pb
      const ta = new Date(a.scheduled_at).getTime()
      const tb = new Date(b.scheduled_at).getTime()
      return pa <= 1 ? ta - tb : tb - ta
    })
    orders.value = list
    const today = dateKey(new Date().toISOString())
    todayCount.value = list.filter((item: any) => dateKey(item.scheduled_at) === today).length
    pendingCount.value = list.filter((item: any) => ['assigned', 'in_service'].includes(item.status)).length
    completedCount.value = list.filter((item: any) => item.status === 'completed').length
  } catch (e: any) {
    showToast(e.message || '加载失败')
  } finally {
    loading.value = false
  }
}

function goRecord(id: number) {
  router.push(`/staff/record/${id}`)
}

onMounted(load)
</script>

<style scoped>
.staff-page { padding: 14px 18px 110px; }
.staff-shell { position: relative; overflow: hidden; padding: 20px 18px 16px; margin-bottom: 14px; border-radius: 28px 22px 30px 22px; background: radial-gradient(circle at 88% 12%, #388C65 0%, #1E6143 52%, #13402B 100%); color: #fff; box-shadow: 0 20px 44px -18px rgba(22,74,51,.4); }
.staff-aura { position: absolute; border-radius: 50%; }
.staff-aura.a { width: 220px; height: 220px; right: -80px; top: -90px; background: radial-gradient(circle, rgba(246,227,186,.22), transparent 70%); }
.staff-aura.b { width: 180px; height: 180px; left: -70px; bottom: -80px; background: radial-gradient(circle, rgba(114,212,166,.16), transparent 70%); }
.shell-top { position: relative; z-index: 1; align-items: flex-start; }
.staff-title { margin: 8px 0 0; font-size: 23px; line-height: 1.3; }
.staff-sub { margin: 5px 0 0; font-size: 10px; color: rgba(255,255,255,.7); }
.staff-avatar { width: 46px; height: 46px; border: none; padding: 0; border-radius: 17px 19px 15px 19px; display: grid; place-items: center; background: linear-gradient(135deg,#FFF7E8,#F6E3BA); color: var(--deep); font-weight: 700; font-size: 18px; flex-shrink: 0; }
.staff-avatar:active { opacity: .82; }
.shell-stats { position: relative; z-index: 1; display: flex; margin-top: 16px; padding-top: 12px; border-top: 1px solid rgba(255,255,255,.14); }
.shell-stat { flex: 1; }
.shell-stat b { display: block; font-size: 18px; color: var(--gold); }
.shell-stat span { display: block; margin-top: 2px; font-size: 9px; color: rgba(255,255,255,.52); }
.order-filter { display: flex; gap: 7px; margin-bottom: 12px; }
.filter-chip { border: none; padding: 8px 13px; border-radius: 999px; background: #F0EFEA; color: var(--sub); font-size: 10px; }
.filter-chip.active { background: var(--primary); color: #fff; font-weight: 700; box-shadow: 0 8px 18px -8px rgba(22,74,51,.35); }
.order-bubble { background: #fff; border-radius: 22px 18px 24px 18px; padding: 15px 16px; margin-bottom: 10px; box-shadow: var(--shadow); }
.order-dot { width: 7px; height: 7px; border-radius: 50%; background: #277A55; margin-right: 7px; box-shadow: 0 0 0 5px rgba(39,122,85,.1); }
.order-service { font-size: 16px; }
.order-meta { margin-top: 5px; padding-left: 14px; font-size: 11px; color: #6E7872; }
.order-hint { margin-top: 8px; padding-top: 8px; border-top: 1px solid var(--line); font-size: 10px; color: var(--muted); }
.order-no { font-size: 9px; color: #B0B5AD; }
.amount { color: var(--coral); font-weight: 800; }
.order-tags { gap: 5px; }
</style>
