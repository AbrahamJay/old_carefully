<template>
  <main class="page no-tab with-action">
    <header class="topbar">
      <button class="back" @click="back">‹</button>
      <span class="topbar-title">订单详情</span>
      <span class="topbar-space"></span>
    </header>

    <div v-if="loading && !order" class="card"><div class="skeleton" style="height: 26px; width: 45%"></div><div class="skeleton mt12" style="height: 14px; width: 75%"></div></div>
    <template v-else-if="order">
      <section class="status-hero">
        <div class="status-top">
          <span class="hero-eyebrow" @click="copyOrderNo">订单 {{ order.order_no }} · 复制</span>
          <span class="tag" :class="statusDisplay.cls">{{ statusDisplay.text }}</span>
        </div>
        <h1>{{ headline }}</h1>
        <p>{{ subline }}</p>
        <div class="status-amount-row"><span>订单金额</span><strong>¥{{ money(order.amount_cents) }}</strong></div>
      </section>

      <section class="card organic">
        <div class="row between"><h2 class="section-title">服务进度</h2><span class="micro muted">{{ statusDisplay.text }}</span></div>
        <div class="timeline">
          <div v-for="step in steps" :key="step.label" class="step" :class="step.state">
            <span class="step-line"></span><span class="step-dot">{{ step.state === 'done' ? '✓' : '' }}</span><span class="step-label">{{ step.label }}</span>
          </div>
        </div>
      </section>

      <section class="card organic">
        <h2 class="section-title">费用</h2>
        <div class="row between mt12"><span class="info-key">订单金额</span><strong>¥{{ money(order.amount_cents) }}</strong></div>
        <div v-if="order.deposit_cents" class="row between mt8"><span class="info-key">定金（30%）</span><span>¥{{ money(order.deposit_cents) }}</span></div>
        <div v-if="order.paid_cents" class="row between mt8"><span class="info-key">已付</span><span>¥{{ money(order.paid_cents) }}</span></div>
        <div v-if="order.refunded_cents" class="row between mt8"><span class="info-key">已退款</span><span>¥{{ money(order.refunded_cents) }}</span></div>
        <div v-if="showRemaining" class="row between mt8"><span class="info-key">待付</span><span class="pay-amount">¥{{ money(order.remaining_cents) }}</span></div>
        <div class="row between mt12"><span class="info-key">支付状态</span><span class="tag" :class="order.payment_status === 'refunded' ? 'tag-gray' : 'tag-completed'">{{ PAY[order.payment_status] || order.payment_status }}</span></div>
        <div v-if="payInfo.label" class="deposit-note mt12">演示环境：{{ payInfo.label }}为模拟支付，不产生真实扣款；取消订单会自动退已付款。</div>
      </section>

      <section class="card organic">
        <h2 class="section-title">服务详情</h2>
        <div class="info-row mt12"><span class="info-key">服务项目</span><span class="info-value">{{ order.service?.name }}</span></div>
        <div class="info-row"><span class="info-key">服务时长</span><span class="info-value">{{ order.service?.duration_minutes }} 分钟</span></div>
        <div class="info-row"><span class="info-key">长辈</span><span class="info-value">{{ order.elder?.name }} {{ order.elder?.phone }}</span></div>
        <div class="info-row"><span class="info-key">服务人员</span><span class="info-value">{{ order.staff?.name || '等待管家安排' }}</span></div>
        <div class="divider"></div>
        <div class="info-block"><span class="info-key">上门地址</span><div class="info-text">{{ order.address }}</div></div>
        <div v-if="order.contact_name" class="info-block"><span class="info-key">联系人</span><div class="info-text">{{ order.contact_name }} {{ order.contact_phone }}</div></div>
        <div v-if="order.notes" class="info-block"><span class="info-key">备注</span><div class="info-text">{{ order.notes }}</div></div>
        <div v-if="order.cancel_reason" class="info-block"><span class="info-key">取消原因</span><div class="info-text">{{ order.cancel_reason }}</div></div>
      </section>

      <section v-if="records.length" class="card organic">
        <h2 class="section-title">服务记录</h2>
        <div v-for="record in records" :key="record.id" class="record">
          <div class="row between">
            <span class="record-time">{{ dateTime(record.checkin_at) }}</span>
            <span class="tag" :class="record.elder_confirmed ? 'tag-completed' : 'tag-pending'">{{ record.elder_confirmed ? '家属已确认' : '待确认' }}</span>
          </div>
          <p>{{ record.content }}</p>
          <div v-if="record.photos?.length" class="photo-grid">
            <img v-for="photo in record.photos" :key="photo" :src="photo" alt="服务照片" @click="preview(photo, record.photos)" />
          </div>
        </div>
      </section>

      <section v-if="canConfirmService" class="card organic">
        <h2 class="section-title">尾款已付，请确认服务完成</h2>
        <p class="small muted mt8">确认后本次服务记录生效，状态变为已完成。如有问题请先联系管家。</p>
        <button class="btn btn-primary btn-block mt16" @click="confirmService">确认服务完成</button>
      </section>

      <section v-if="order.status === 'completed' && !order.review" class="card organic">
        <h2 class="section-title">评价这次服务</h2>
        <div class="stars mt12">
          <button v-for="n in 5" :key="n" class="star" :class="{ on: rating >= n }" @click="rating = n">★</button>
        </div>
        <textarea v-model="reviewContent" class="textarea mt12" placeholder="服务怎么样？写两句吧" />
        <button class="btn btn-primary btn-block mt12" @click="submitReview">提交评价</button>
      </section>

      <section v-else-if="order.review" class="card organic">
        <h2 class="section-title">我的评价</h2>
        <div class="stars mt8"><span v-for="n in 5" :key="n" class="star" :class="{ on: order.review.rating >= n }">★</span></div>
        <p class="small muted mt8">{{ order.review.content }}</p>
      </section>
    </template>

    <div v-if="order" class="action-bar">
      <button class="btn btn-ghost" @click="callSteward">联系管家</button>
      <button v-if="payInfo.label" class="btn btn-primary" @click="pay">{{ payInfo.label }} ¥{{ money(payInfo.label === '付定金' ? Number(order.deposit_cents || 0) - Number(order.paid_cents || 0) : order.remaining_cents) }}</button>
      <button v-else-if="canConfirmService" class="btn btn-primary" @click="confirmService">确认完成</button>
      <button v-else-if="canCancel" class="btn btn-primary" @click="cancel">取消订单</button>
      <button v-else-if="order.status === 'completed'" class="btn btn-primary" @click="router.push('/create')">再来一单</button>
      <button v-else class="btn btn-primary" @click="callSteward">联系管家</button>
    </div>
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { get, post } from '../api/http'
import { SERVICE_PHONE } from '../constants'
import { dateTime, displayStatus, money, payAction, PAY } from '../api/format'
import { showToast } from '../stores/toast'

const route = useRoute()
const router = useRouter()
const id = Number(route.params.id)
const order = ref<any>(null)
const loading = ref(true)
const rating = ref(5)
const reviewContent = ref('')

const records = computed(() => order.value?.records || [])
const statusDisplay = computed(() => displayStatus(order.value || { status: '', payment_status: '' }))
const payInfo = computed(() => payAction(order.value || {}))
const showRemaining = computed(() => Number(order.value?.remaining_cents || 0) > 0 && order.value?.status !== 'cancelled' && order.value?.payment_status !== 'refunded')
const canCancel = computed(() => ['pending_confirm', 'confirmed', 'assigned'].includes(order.value?.status))
const canConfirmService = computed(() => {
  if (!order.value || order.value.status !== 'completed') return false
  if (order.value.payment_status === 'refunded') return false
  if (Number(order.value.remaining_cents || 0) > 0) return false
  const latest = records.value[records.value.length - 1]
  return !!latest && !latest.elder_confirmed
})

const headline = computed(() => {
  if (!order.value) return ''
  // pending_confirm 的展示文案也是“待确认”，必须限定 completed，避免刚付定金就被误判为服务已完成
  if (order.value.status === 'completed' && statusDisplay.value.text === '待付尾款') return '服务已完成，待付尾款'
  if (order.value.status === 'completed' && statusDisplay.value.text === '待确认') return '服务已完成，请确认'
  if (statusDisplay.value.text === '已退款') return '订单已退款'
  if (order.value.status === 'completed') return '服务已完成'
  if (order.value.status === 'in_service') return '服务进行中'
  if (order.value.status === 'assigned') return '已安排服务人员'
  if (order.value.status === 'confirmed') return '已确认，等待派单'
  if (order.value.status === 'cancelled') return '订单已取消'
  return '等管家确认'
})
const subline = computed(() => {
  if (!order.value) return ''
  if (order.value.status === 'completed') {
    if (statusDisplay.value.text === '待付尾款') return `尾款 ¥${money(order.value.remaining_cents)} · 结清并确认后显示已完成`
    if (statusDisplay.value.text === '待确认') return '尾款已结清 · 确认服务后显示已完成'
  }
  return `${order.value.staff?.name ? order.value.staff.name + ' · ' : ''}预约 ${dateTime(order.value.scheduled_at)}`
})

const steps = computed(() => {
  if (!order.value) return []
  const labels = ['提交', '派单', '服务中', '完成']
  const indexMap: Record<string, number> = { pending_confirm: 0, confirmed: 1, assigned: 2, in_service: 2, completed: 3, cancelled: -1 }
  const current = indexMap[order.value.status] ?? 0
  return labels.map((label, index) => ({
    label,
    state: order.value.status === 'completed' ? 'done' : order.value.status !== 'cancelled' && index < current ? 'done' : order.value.status !== 'cancelled' && index === current ? 'current' : 'todo'
  }))
})

async function load() {
  loading.value = true
  try {
    order.value = await get(`/orders/${id}`)
    rating.value = order.value?.review?.rating || 5
  } catch (e: any) {
    showToast(e.message || '加载失败')
  } finally {
    loading.value = false
  }
}

function back() {
  if (history.length > 1) router.back()
  else router.push('/orders')
}

function copyOrderNo() {
  navigator.clipboard?.writeText(order.value.order_no)
  showToast('订单号已复制')
}

function callSteward() {
  location.href = 'tel:' + SERVICE_PHONE
}

async function pay() {
  if (!confirm(`确认模拟支付${payInfo.value.label}？`)) return
  try {
    await post(`/orders/${id}/pay`)
    showToast('模拟支付成功')
    await load()
  } catch (e: any) {
    showToast(e.message || '支付失败')
  }
}

async function cancel() {
  if (!confirm('确认取消这个订单？已付款会自动退款。')) return
  try {
    await post(`/orders/${id}/cancel`)
    showToast('已取消')
    await load()
  } catch (e: any) {
    showToast(e.message || '取消失败')
  }
}

async function confirmService() {
  try {
    await post(`/orders/${id}/confirm-service`)
    showToast('已确认服务完成')
    await load()
  } catch (e: any) {
    showToast(e.message || '确认失败')
  }
}

async function submitReview() {
  try {
    await post(`/orders/${id}/review`, { rating: rating.value, content: reviewContent.value })
    showToast('评价成功')
    await load()
  } catch (e: any) {
    showToast(e.message || '评价失败')
  }
}

function preview(current: string, list: string[]) {
  window.open(current, '_blank')
}

onMounted(load)
</script>

<style scoped>
.status-hero { position: relative; overflow: hidden; border-radius: 30px 24px 32px 24px; padding: 20px; background: radial-gradient(circle at 88% 12%, #388C65 0%, #1E6143 52%, #13402B 100%); color: #fff; box-shadow: 0 20px 44px -18px rgba(22,74,51,.4); margin-bottom: 12px; }
.status-top { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.hero-eyebrow { font-size: 9px; color: rgba(255,255,255,.55); }
.status-hero h1 { margin: 18px 0 0; font-size: 24px; line-height: 1.3; }
.status-hero p { margin: 5px 0 0; font-size: 11px; color: rgba(255,255,255,.68); }
.status-amount-row { display: flex; align-items: center; justify-content: space-between; margin-top: 18px; padding-top: 12px; border-top: 1px solid rgba(255,255,255,.14); font-size: 10px; color: rgba(255,255,255,.55); }
.status-amount-row strong { font-size: 22px; color: var(--gold); }
.pay-amount { color: var(--coral); font-weight: 800; }
.record { padding: 14px 0; border-bottom: 1px solid var(--line); }
.record:last-child { border-bottom: none; }
.record-time { font-size: 10px; color: var(--muted); }
.record p { margin: 7px 0 0; font-size: 13px; line-height: 1.7; }
.photo-grid { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 10px; }
.photo-grid img { width: 88px; height: 88px; object-fit: cover; border-radius: 14px; }
.stars { display: flex; gap: 6px; }
.star { border: none; background: transparent; padding: 0; color: #D8D5CC; font-size: 28px; line-height: 1; }
.star.on { color: var(--gold); }
</style>
