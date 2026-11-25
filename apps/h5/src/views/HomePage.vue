<template>
  <main class="page home-page">
    <section class="hero-shell">
      <div class="hero-aura aura-1"></div>
      <div class="hero-aura aura-2"></div>
      <div class="row between hero-head">
        <div class="grow">
          <div class="status-pill"><i class="pulse-dot"></i><span>{{ statusLine }}</span></div>
          <h1 class="hero-greeting">{{ greeting }}，{{ auth.user?.name || '家人' }}</h1>
        </div>
        <div class="hero-avatar" @click="router.push('/profile')">{{ avatarText }}</div>
      </div>
      <div class="hero-dock">
        <button class="dock-btn main" @click="goCreate()">
          <span class="dock-icon">约</span>
          <span><b class="dock-title">一键预约</b><small class="dock-sub">陪诊 · 保洁 · 代办</small></span>
        </button>
        <button class="dock-btn sub" @click="router.push('/elders')">
          <span class="dock-icon warm">家</span>
          <span><b class="dock-title">长辈档案</b><small class="dock-sub">地址与健康备注</small></span>
        </button>
      </div>
    </section>

    <div class="section-head"><h2 class="section-title">为您精选照护</h2><button class="section-action" @click="goCreate()">全部服务 ›</button></div>

    <div v-if="loading" class="card"><div class="skeleton" style="height: 20px; width: 40%"></div><div class="skeleton mt12" style="height: 12px; width: 75%"></div></div>
    <template v-else-if="services.length">
      <button v-if="featuredService" class="bento-featured" @click="goCreate(featuredService.id)">
        <div class="featured-glow"></div>
        <div class="row between">
          <span class="featured-badge">口碑首选 · 专人全程陪同</span>
          <span class="featured-price">¥{{ featuredService.priceText }}<small class="unit">/{{ featuredService.unit }}</small></span>
        </div>
        <div class="featured-main">
          <span class="featured-seal">{{ featuredService.iconText }}</span>
          <span class="grow"><b class="featured-title">{{ featuredService.name }}</b><small class="featured-desc">{{ featuredService.description }}</small></span>
          <span class="featured-cta">去预约</span>
        </div>
      </button>
      <div v-if="secondaryServices.length" class="bento-duo">
        <button v-for="(service, index) in secondaryServices" :key="service.id" class="duo-card" :class="{ 'warm-tint': index === 1 }" @click="goCreate(service.id)">
          <div class="row between"><span class="duo-icon">{{ service.iconText }}</span><span class="duo-price">¥{{ service.priceText }}</span></div>
          <div class="duo-title">{{ service.name }}</div>
          <div class="duo-sub">{{ service.duration_minutes }}分钟 · 上门服务</div>
        </button>
      </div>
      <div class="capsule-strip">
        <button v-for="service in capsuleServices" :key="service.id" class="mini-capsule" @click="goCreate(service.id)">
          <span class="cap-dot">{{ service.iconText }}</span><span class="cap-name">{{ service.name }}</span><span class="cap-price">¥{{ service.priceText }}</span>
        </button>
        <button class="mini-capsule urgent" @click="router.push('/emergency')"><span class="cap-dot urgent">急</span><span class="cap-name">紧急联系</span><span class="cap-price">120 / 社区</span></button>
      </div>
    </template>
    <div v-else class="card organic empty">
      <div class="empty-mark">候</div><div class="empty-title">服务正在整理中</div><div class="empty-desc">暂时没有上架服务，直接联系管家帮您安排。</div>
      <button class="btn btn-primary" @click="callSteward">联系管家</button>
    </div>

    <button v-if="isStaff" class="staff-banner" @click="router.push('/staff/orders')">
      <span class="staff-seal">工</span><span class="grow"><b class="list-title">进入员工接单工作台</b><small class="list-desc">接单上门 · 拍照留痕 · 服务完成</small></span><span class="staff-go">去处理</span>
    </button>

    <div class="section-head"><h2 class="section-title">跟进中的服务</h2><button class="section-action" @click="router.push('/orders')">全部 ›</button></div>
    <template v-if="orders.length">
      <button v-for="order in orders" :key="order.id" class="order-bubble" @click="router.push(`/orders/${order.id}`)">
        <div class="row between"><div class="row"><i class="order-dot"></i><b class="order-service">{{ order.service_name }}</b></div><span class="tag" :class="order.statusCls">{{ order.statusText }}</span></div>
        <div class="order-meta">{{ order.elder_name }} · 预约 {{ order.timeText }}</div>
        <div class="row between mt16"><span class="order-no">{{ order.order_no }}</span><span class="order-amount">¥{{ order.amountText }} <span class="chevron">›</span></span></div>
      </button>
    </template>
    <div v-else class="card organic empty">
      <div class="empty-mark">暖</div><div class="empty-title">还没有预约记录</div><div class="empty-desc">点选上方服务，管家会第一时间跟进安排。</div>
      <button class="btn btn-primary" @click="goCreate()">预约第一次服务</button>
    </div>

    <button class="steward-island" @click="callSteward">
      <span class="steward-avatar">管</span><span class="grow"><b class="steward-title">社区专属养老管家</b><small class="steward-sub">不方便打字？点此直接电话帮您安排</small></span><span class="steward-call">呼叫</span>
    </button>
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { get } from '../api/http'
import { auth } from '../stores/auth'
import { SERVICE_PHONE } from '../constants'
import { dateTime, displayStatus, money } from '../api/format'

const router = useRouter()
const services = ref<any[]>([])
const orders = ref<any[]>([])
const loading = ref(true)
const greeting = ref('你好')
const statusLine = ref('贴心管家在线，随时响应长辈需求')
const isStaff = computed(() => auth.user?.role === 'staff')

const featuredService = computed(() => services.value[0] || null)
const secondaryServices = computed(() => services.value.slice(1, 3))
const capsuleServices = computed(() => services.value.slice(3))
const avatarText = computed(() => auth.user?.name?.slice(0, 1) || '家')

async function load() {
  loading.value = true
  try {
    const hour = new Date().getHours()
    greeting.value = hour < 11 ? '早安' : hour < 18 ? '午安' : '晚安'
    const [serviceData, orderData] = await Promise.all([get<any[]>('/services'), get<any>('/orders?page=1&page_size=5')])
    services.value = (serviceData || []).map(item => ({ ...item, iconText: item.name?.slice(0, 1) || '服', priceText: money(item.price_cents) }))
    orders.value = (orderData.items || []).map((item: any) => {
      const status = displayStatus(item)
      return { ...item, statusText: status.text, statusCls: status.cls, amountText: money(item.amount_cents), timeText: dateTime(item.scheduled_at) }
    })
    const active = orders.value.filter(item => ['pending_confirm', 'confirmed', 'assigned', 'in_service'].includes(item.status)).length
    statusLine.value = active > 0 ? `当前有 ${active} 项照护服务正在跟进` : '贴心管家在线，随时响应长辈需求'
  } finally {
    loading.value = false
  }
}

function goCreate(serviceId?: number) {
  router.push('/create' + (serviceId ? `?serviceId=${serviceId}` : ''))
}

function callSteward() { location.href = 'tel:' + SERVICE_PHONE }

onMounted(load)
</script>

<style scoped>
.home-page { padding: 22px 18px 108px; }
.hero-shell { position: relative; overflow: hidden; padding: 5.0667cqw 4.5333cqw 4.5333cqw; border-radius: 6.4cqw 5.3333cqw 7.4667cqw 4.8cqw; background: radial-gradient(circle at 88% 14%, #388C65 0%, #1E6143 52%, #13402B 100%); color: #fff; box-shadow: 0 3.2cqw 6.9333cqw -1.6cqw rgba(22,74,51,.24); }
.hero-aura { position: absolute; border-radius: 50%; }
.aura-1 { width: 48cqw; height: 48cqw; right: -16cqw; top: -16cqw; background: radial-gradient(circle, rgba(246,227,186,.24), transparent 70%); }
.aura-2 { width: 37.3333cqw; height: 37.3333cqw; left: -10.6667cqw; bottom: -13.3333cqw; background: radial-gradient(circle, rgba(114,212,166,.18), transparent 70%); }
.hero-head { position: relative; z-index: 1; align-items: flex-start; }
.status-pill { display: inline-flex; align-items: center; gap: 1.6cqw; padding: 1.0667cqw 2.9333cqw; border-radius: 999px; background: rgba(255,255,255,.13); font-size: 2.9333cqw; color: rgba(255,255,255,.9); }
.pulse-dot { width: 1.8667cqw; height: 1.8667cqw; border-radius: 50%; background: #A9F5CE; box-shadow: 0 0 0 .8cqw rgba(169,245,206,.25); }
.hero-greeting { margin: 2.4cqw 0 0; font-size: 6.1333cqw; line-height: 1.25; font-weight: 700; letter-spacing: .0667cqw; }
.hero-avatar { width: 12.8cqw; height: 12.8cqw; border-radius: 4.8cqw 5.3333cqw 4.2667cqw 5.3333cqw; background: linear-gradient(135deg,#FFF7E8,#F6E3BA); color: #164A33; display: grid; place-items: center; font-size: 5.0667cqw; font-weight: 700; box-shadow: 0 1.6cqw 3.7333cqw rgba(0,0,0,.12); flex-shrink: 0; }
.hero-dock { position: relative; z-index: 1; display: flex; gap: 2.4cqw; margin-top: 4.5333cqw; }
.dock-btn { flex: 1; display: flex; align-items: center; gap: 2.1333cqw; padding: 2.6667cqw 2.9333cqw; border-radius: 4.2667cqw; background: rgba(255,255,255,.12); border: .1333cqw solid rgba(255,255,255,.18); text-align: left; }
.dock-btn.main { background: #fff; color: #1A2420; box-shadow: 0 1.8667cqw 4cqw rgba(14,46,31,.18); }
.dock-icon { width: 8.5333cqw; height: 8.5333cqw; border-radius: 2.9333cqw; background: #E6F3EC; color: #1F6345; display: grid; place-items: center; font-size: 3.7333cqw; font-weight: 700; flex-shrink: 0; }
.dock-icon.warm { background: rgba(246,227,186,.22); color: #F6E3BA; }
.dock-title { display: block; font-size: 3.7333cqw; }
.dock-sub { display: block; margin-top: .2667cqw; font-size: 2.8cqw; opacity: .72; }
.section-head { display: flex; align-items: center; justify-content: space-between; margin: 3.7333cqw .5333cqw 1.8667cqw; }
.section-title { font-size: 3.7333cqw; font-weight: 700; }
.section-action { border: none; background: #E6F3EC; color: #1F6345; padding: 1.3333cqw 2.6667cqw; border-radius: 999px; font-size: 2.4cqw; }
.bento-featured { position: relative; overflow: hidden; display: block; width: 100%; text-align: left; padding: 4cqw 4cqw 3.7333cqw; border: none; border-radius: 5.6cqw 4.8cqw 6.1333cqw 4.5333cqw; background: linear-gradient(135deg,#fff,#FFF7F0); box-shadow: 0 2.6667cqw 6.4cqw -1.6cqw rgba(232,122,72,.12), 0 .5333cqw 1.8667cqw rgba(22,74,51,.04); }
.featured-glow { position: absolute; width: 32cqw; height: 32cqw; right: -8cqw; top: -10.6667cqw; border-radius: 50%; background: radial-gradient(circle, rgba(232,122,72,.14), transparent 70%); }
.featured-badge { padding: .8cqw 2.6667cqw; border-radius: 999px; background: #FFF0E6; color: #D96B38; font-size: 2.4cqw; font-weight: 600; }
.featured-price { font-size: 5.0667cqw; font-weight: 700; color: #E87A48; }
.featured-price .unit { font-size: 2.4cqw; color: #8C9690; font-weight: 500; }
.featured-main { position: relative; display: flex; align-items: center; gap: 2.9333cqw; margin-top: 2.9333cqw; }
.featured-seal { width: 12.2667cqw; height: 12.2667cqw; border-radius: 4.2667cqw 4.8cqw 3.7333cqw 4.8cqw; background: linear-gradient(135deg,#277A55,#164A33); color: #fff; display: grid; place-items: center; font-size: 5.0667cqw; font-weight: 700; flex-shrink: 0; }
.featured-title { display: block; font-size: 4.5333cqw; font-weight: 700; }
.featured-desc { display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; margin-top: .8cqw; font-size: 3.2cqw; line-height: 1.5; color: #6E7872; }
.featured-cta { padding: 1.8667cqw 3.7333cqw; border-radius: 999px; background: #1F6345; color: #fff; font-size: 3.3333cqw; font-weight: 600; flex-shrink: 0; }
.bento-duo { display: flex; gap: 2.6667cqw; margin-top: 2.6667cqw; }
.duo-card { flex: 1; text-align: left; border: none; padding: 3.7333cqw 3.4667cqw; border-radius: 4.8cqw 5.6cqw 4.5333cqw 5.3333cqw; background: #fff; box-shadow: 0 2.1333cqw 5.3333cqw -1.6cqw rgba(22,74,51,.06); }
.duo-card.warm-tint { background: linear-gradient(145deg,#fff,#F4FAF6); border-radius: 5.6cqw 4.5333cqw 5.3333cqw 4.8cqw; }
.duo-icon { width: 9.6cqw; height: 9.6cqw; border-radius: 3.2cqw 3.7333cqw 2.9333cqw 3.4667cqw; background: #E6F3EC; color: #1F6345; display: grid; place-items: center; font-size: 4cqw; font-weight: 700; }
.duo-price { font-size: 4cqw; font-weight: 700; color: #E87A48; }
.duo-title { margin-top: 2.6667cqw; font-size: 4.1333cqw; font-weight: 700; }
.duo-sub { margin-top: .8cqw; font-size: 3.0667cqw; color: #8C9690; }
.capsule-strip { white-space: nowrap; overflow-x: auto; margin-top: 2.6667cqw; padding-bottom: 2px; scrollbar-width: none; }
.capsule-strip::-webkit-scrollbar { display: none; }
.mini-capsule { display: inline-flex; align-items: center; gap: 1.6cqw; padding: 1.8667cqw 3.4667cqw 1.8667cqw 2.1333cqw; margin-right: 2.1333cqw; border: none; border-radius: 999px; background: #fff; box-shadow: 0 .8cqw 3.4667cqw -1.0667cqw rgba(22,74,51,.06); }
.mini-capsule.urgent { background: #FFF2EC; }
.cap-dot { width: 6.4cqw; height: 6.4cqw; border-radius: 50%; background: #E6F3EC; color: #1F6345; display: grid; place-items: center; font-size: 3.2cqw; font-weight: 700; }
.cap-dot.urgent { background: #E87A48; color: #fff; }
.cap-name { font-size: 3.4667cqw; font-weight: 600; }
.cap-price { font-size: 3.0667cqw; color: #E87A48; font-weight: 600; }
.order-bubble { display: block; width: 100%; text-align: left; border: none; background: #fff; border-radius: 5.0667cqw 4.5333cqw 5.6cqw 4.5333cqw; padding: 3.7333cqw 4cqw; margin-bottom: 2.4cqw; box-shadow: 0 2.1333cqw 5.3333cqw -1.6cqw rgba(22,74,51,.06); }
.order-dot { width: 2.1333cqw; height: 2.1333cqw; border-radius: 50%; background: #277A55; margin-right: 1.8667cqw; }
.order-service { font-size: 4.1333cqw; font-weight: 700; }
.order-meta { margin-top: 1.3333cqw; padding-left: 4cqw; font-size: 3.3333cqw; color: #6E7872; }
.order-no { font-size: 10px; color: #B0B5AD; }
.order-amount { font-size: 4cqw; color: #E87A48; font-weight: 800; }
.staff-banner { display: flex; align-items: center; gap: 2.6667cqw; width: 100%; border: none; margin-top: 3.4667cqw; padding: 3.4667cqw 3.7333cqw; border-radius: 5.0667cqw; background: linear-gradient(135deg,#FFF5EC,#FFEAD9); text-align: left; }
.staff-seal { width: 10.1333cqw; height: 10.1333cqw; border-radius: 3.4667cqw; background: #E87A48; color: #fff; display: grid; place-items: center; font-size: 4cqw; font-weight: 700; }
.staff-go { padding: 1.6cqw 3.4667cqw; border-radius: 999px; background: #E87A48; color: #fff; font-size: 3.2cqw; font-weight: 600; }
.steward-island { display: flex; align-items: center; gap: 2.6667cqw; width: 100%; border: none; margin-top: 3.7333cqw; padding: 3.2cqw 3.7333cqw; border-radius: 999px; background: linear-gradient(135deg,#1E6143,#143D2A); color: #fff; text-align: left; box-shadow: 0 2.6667cqw 5.8667cqw -1.6cqw rgba(22,74,51,.25); }
.steward-avatar { width: 10.1333cqw; height: 10.1333cqw; border-radius: 50%; background: #F6E3BA; color: #164A33; display: grid; place-items: center; font-size: 4cqw; font-weight: 700; flex-shrink: 0; }
.steward-title { display: block; font-size: 3.8667cqw; font-weight: 700; }
.steward-sub { display: block; margin-top: .2667cqw; font-size: 2.9333cqw; color: rgba(255,255,255,.72); }
.steward-call { padding: 1.8667cqw 4cqw; border-radius: 999px; background: #F6E3BA; color: #164A33; font-size: 3.3333cqw; font-weight: 700; }
.skeleton { border-radius: 999px; background: linear-gradient(90deg,#F2F1EC,#FAF9F5,#F2F1EC); }
</style>
