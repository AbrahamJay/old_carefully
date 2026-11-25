<template>
  <main class="page">
    <header class="page-head">
      <div>
        <span class="eyebrow">MY SERVICES</span>
        <h1>我的订单</h1>
        <p>共 {{ orders.length }} 条服务记录</p>
      </div>
      <button class="btn btn-primary small-btn" @click="router.push('/create')">新预约</button>
    </header>

    <div class="tabs">
      <button v-for="tab in tabs" :key="tab.key" class="chip" :class="{ active: current === tab.key }" @click="setTab(tab.key)">{{ tab.label }}</button>
    </div>

    <div v-if="loading && !orders.length" class="card"><div class="skeleton" style="height: 22px; width: 45%"></div><div class="skeleton mt12" style="height: 12px; width: 80%"></div></div>
    <div v-else-if="!orders.length" class="card empty">
      <div class="empty-mark">单</div>
      <div class="empty-title">还没有订单</div>
      <div class="empty-desc">预约一次陪诊或保洁，让服务先跑起来。</div>
      <button class="btn btn-primary" @click="router.push('/create')">去预约</button>
    </div>

    <article v-for="order in orders" :key="order.id" class="order-card" @click="router.push(`/orders/${order.id}`)">
      <div class="row between">
        <div class="row"><i class="dot"></i><strong>{{ order.service_name }}</strong></div>
        <span class="tag" :class="displayStatus(order).cls">{{ displayStatus(order).text }}</span>
      </div>
      <div class="order-meta">{{ order.elder_name }} · 预约 {{ dateTime(order.scheduled_at) }}</div>
      <div class="row between mt12">
        <span class="order-no">{{ order.order_no }}</span>
        <span class="order-amount">¥{{ money(order.amount_cents) }} <span class="chevron">›</span></span>
      </div>
      <div v-if="payAction(order).label" class="pay-line">
        <span>{{ payAction(order).hint }} · {{ payStatusText(order.payment_status) }}</span>
        <button class="pay-btn" @click.stop="pay(order)">{{ payAction(order).label }}</button>
      </div>
    </article>
  </main>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { get, post } from '../api/http'
import { dateTime, displayStatus, money, payAction, PAY } from '../api/format'
import { showToast } from '../stores/toast'

const router = useRouter()
const tabs = [
  { key: '', label: '全部' },
  { key: 'pending_confirm', label: '待确认' },
  { key: 'assigned', label: '已派单' },
  { key: 'in_service', label: '服务中' },
  { key: 'completed', label: '已完成' }
]
const current = ref('')
const orders = ref<any[]>([])
const loading = ref(true)

function payStatusText(status: string) {
  return PAY[status] || status
}

function setTab(key: string) {
  current.value = key
  load()
}

async function load() {
  loading.value = true
  try {
    const query = current.value ? `&status=${current.value}` : ''
    const data = await get<any>(`/orders?page=1&page_size=50${query}`)
    orders.value = data.items || []
  } finally {
    loading.value = false
  }
}

async function pay(order: any) {
  if (!confirm(`确认模拟支付${payAction(order).label}？`)) return
  try {
    await post(`/orders/${order.id}/pay`)
    showToast('模拟支付成功')
    await load()
  } catch (e: any) {
    showToast(e.message || '支付失败')
  }
}

onMounted(load)
</script>

<style scoped>
.page-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; margin-bottom: 16px; }
.page-head h1 { margin: 6px 0 0; font-size: 28px; }
.page-head p { margin: 5px 0 0; font-size: 11px; color: var(--muted); }
.small-btn { padding: 10px 16px; font-size: 12px; flex-shrink: 0; }
.tabs { display: flex; gap: 7px; overflow-x: auto; padding-bottom: 4px; margin-bottom: 12px; scrollbar-width: none; }
.tabs::-webkit-scrollbar { display: none; }
.order-card { background: #fff; border-radius: 22px 18px 24px 18px; padding: 16px; margin-bottom: 10px; box-shadow: var(--shadow); }
.order-card:active { opacity: .84; }
.dot { width: 7px; height: 7px; border-radius: 50%; background: var(--mint); margin-right: 7px; box-shadow: 0 0 0 5px rgba(58,142,104,.09); }
.order-meta { margin-top: 7px; padding-left: 14px; font-size: 11px; color: var(--sub); }
.order-no { font-size: 9px; color: #B0B5AD; }
.order-amount { font-size: 15px; color: var(--coral); font-weight: 800; }
.pay-line { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-top: 10px; padding-top: 10px; border-top: 1px solid var(--line); font-size: 10px; color: #C25E0A; }
.pay-btn { border: none; padding: 6px 13px; border-radius: 999px; background: var(--primary); color: #fff; font-size: 10px; font-weight: 700; }
.skeleton { border-radius: 999px; background: linear-gradient(90deg, #F2F1EC, #FAF9F5, #F2F1EC); }
</style>
