<template>
  <main class="page no-tab with-action">
    <header class="topbar">
      <button class="back" @click="back">‹</button>
      <span class="topbar-title">预约服务</span>
      <span class="topbar-space"></span>
    </header>

    <div class="page-intro">
      <span class="eyebrow">BOOK A SERVICE</span>
      <h1>预约服务</h1>
      <p>选好服务与时间，提交后立即支付定金。</p>
    </div>

    <div v-if="loading" class="card"><div class="skeleton" style="height: 20px; width: 40%"></div><div class="skeleton mt12" style="height: 12px; width: 75%"></div></div>
    <template v-else>
      <section class="card organic">
        <div class="row between"><h2 class="section-title">1 · 选择长辈</h2><button class="mini-link" @click="router.push('/elders/new')">新增长辈</button></div>
        <div v-if="elders.length" class="elder-scroll">
          <button v-for="elder in elders" :key="elder.id" class="elder-chip" :class="{ active: form.elder_id === elder.id }" @click="selectElder(elder)">
            <span class="elder-avatar">{{ elder.name.slice(0, 1) }}</span>
            <span><strong>{{ elder.name }}</strong><small>{{ elder.address || '未填地址' }}</small></span>
          </button>
        </div>
        <div v-else class="empty-inline">
          <p>还没有长辈档案，先建一份。</p>
          <button class="btn btn-primary" @click="router.push('/elders/new')">新增长辈</button>
        </div>
      </section>

      <section class="card organic">
        <h2 class="section-title">2 · 选择服务</h2>
        <div class="service-scroll">
          <button v-for="service in services" :key="service.id" class="service-chip" :class="{ active: form.service_id === service.id }" @click="selectService(service)">
            <span class="row between"><span class="service-icon">{{ service.name.slice(0, 1) }}</span><b>¥{{ money(service.price_cents) }}</b></span>
            <strong>{{ service.name }}</strong>
            <small>{{ service.duration_minutes }} 分钟 · {{ service.unit }}</small>
          </button>
        </div>
      </section>

      <section class="card organic">
        <h2 class="section-title">3 · 选择时间</h2>
        <div class="label mt12">日期</div>
        <div class="chip-row">
          <button v-for="day in quickDates" :key="day.value" class="chip" :class="{ active: form.date === day.value }" @click="form.date = day.value">{{ day.label }}</button>
          <input v-model="form.date" class="date-input" type="date" />
        </div>
        <div class="label mt16">时间段</div>
        <div class="chip-row">
          <button v-for="time in quickTimes" :key="time" class="chip" :class="{ active: form.time === time }" @click="form.time = time">{{ time }}</button>
          <input v-model="form.time" class="time-input" type="time" />
        </div>
        <div class="selected-note">已选：{{ form.date }} {{ form.time }}</div>
      </section>

      <section class="card organic">
        <h2 class="section-title">4 · 上门信息</h2>
        <div class="field"><div class="label required">服务地址</div><input v-model="form.address" class="input" placeholder="楼栋 / 单元 / 门牌" /></div>
        <div class="two-col">
          <div class="field"><div class="label">联系人</div><input v-model="form.contact_name" class="input" placeholder="联系人" /></div>
          <div class="field"><div class="label">电话</div><input v-model="form.contact_phone" class="input" inputmode="numeric" placeholder="电话" /></div>
        </div>
        <div class="field"><div class="label">备注（可选）</div><textarea v-model="form.notes" class="textarea" placeholder="例如：周三上午复查，需要提前取号；家里有电梯。" /></div>
        <div class="helper">陪诊不提供诊疗、不代问诊；紧急情况请直接拨打 120。</div>
      </section>

      <section class="deposit-card">
        <div class="row between"><span>本次预估</span><strong>¥{{ money(selectedService?.price_cents) }}</strong></div>
        <div class="row between mt8"><span>需付定金（30%）</span><strong>¥{{ money(depositCents) }}</strong></div>
        <p>提交预约时即支付定金；尾款服务完成后支付，取消订单会自动退已付款。</p>
      </section>
    </template>

    <div class="action-bar">
      <div class="action-price"><small>需付定金</small><strong>¥{{ money(depositCents) }}</strong></div>
      <button class="btn btn-primary" :disabled="loading || submitting || !form.elder_id || !form.service_id" @click="submit">
        {{ submitting ? '支付中…' : '预约并付定金' }}
      </button>
    </div>
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { get, post } from '../api/http'
import { money } from '../api/format'
import { showToast } from '../stores/toast'

const route = useRoute()
const router = useRouter()
const elders = ref<any[]>([])
const services = ref<any[]>([])
const loading = ref(true)
const submitting = ref(false)

function localDate(offset = 0) {
  const d = new Date(Date.now() + offset * 86400000)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

const quickDates = [
  { label: '明天', value: localDate(1) },
  { label: '后天', value: localDate(2) },
  { label: '三天后', value: localDate(3) }
]
const quickTimes = ['09:00', '10:00', '14:30', '16:00']
const form = reactive({
  elder_id: 0,
  service_id: 0,
  date: localDate(1),
  time: '09:00',
  address: '',
  contact_name: '',
  contact_phone: '',
  notes: ''
})

const selectedService = computed(() => services.value.find(item => item.id === form.service_id) || null)
const depositCents = computed(() => Math.round(Number(selectedService.value?.price_cents || 0) * 0.3))

function selectElder(elder: any) {
  form.elder_id = elder.id
  form.address = elder.address || ''
  form.contact_name = elder.name || ''
  form.contact_phone = elder.phone || ''
}

function selectService(service: any) {
  form.service_id = service.id
}

function back() {
  if (history.length > 1) router.back()
  else router.push('/')
}

async function load() {
  loading.value = true
  try {
    const [elderData, serviceData, completed] = await Promise.all([
      get<any[]>('/elders'),
      get<any[]>('/services'),
      get<any>('/orders?status=completed&page_size=50')
    ])
    const unpaid = (completed.items || []).find((item: any) => Number(item.remaining_cents || 0) > 0 && item.payment_status !== 'refunded')
    if (unpaid) {
      showToast('有未结清尾款，请先结清后再预约')
      router.replace(`/orders/${unpaid.id}`)
      return
    }
    elders.value = elderData || []
    services.value = serviceData || []
    if (elders.value[0]) selectElder(elders.value[0])
    const preset = Number(route.query.serviceId || 0)
    const selected = services.value.find(item => item.id === preset) || services.value[0]
    if (selected) selectService(selected)
  } catch (e: any) {
    showToast(e.message || '加载失败')
  } finally {
    loading.value = false
  }
}

async function submit() {
  if (submitting.value) return
  if (!form.elder_id || !form.service_id) {
    showToast('请选择长辈和服务')
    return
  }
  const scheduled = `${form.date}T${form.time}:00`
  submitting.value = true
  try {
    const order = await post<any>('/orders', {
      elder_id: form.elder_id,
      service_id: form.service_id,
      scheduled_at: scheduled,
      address: form.address,
      contact_name: form.contact_name,
      contact_phone: form.contact_phone,
      notes: form.notes
    })
    // 预约即付定金：创建成功后立刻发起支付；支付失败不阻断下单，可到详情页重试
    if (Number(order.deposit_cents || 0) > 0) {
      try {
        await post(`/orders/${order.id}/pay`)
        showToast('预约成功，定金已支付')
      } catch (e: any) {
        showToast(e.message || '预约已提交，定金待支付')
      }
    } else {
      showToast('预约已提交')
    }
    router.replace(`/orders/${order.id}`)
  } catch (e: any) {
    showToast(e.message || '预约失败')
  } finally {
    submitting.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.page-intro { margin: 0 2px 16px; }
.page-intro h1 { margin: 6px 0 0; font-size: 27px; }
.page-intro p { margin: 4px 0 0; font-size: 11px; color: var(--muted); }
.mini-link { border: none; background: var(--soft); color: var(--primary); padding: 5px 10px; border-radius: 999px; font-size: 10px; font-weight: 700; }
.elder-scroll, .service-scroll { display: flex; gap: 8px; overflow-x: auto; padding: 4px 0 2px; margin-top: 10px; scrollbar-width: none; }
.elder-scroll::-webkit-scrollbar, .service-scroll::-webkit-scrollbar { display: none; }
.elder-chip { display: flex; align-items: center; gap: 8px; border: 1.5px solid transparent; background: #F6F5F1; padding: 8px 12px 8px 8px; border-radius: 999px; white-space: nowrap; text-align: left; flex-shrink: 0; }
.elder-chip.active { background: #EBF5F0; border-color: var(--primary); }
.elder-avatar { width: 28px; height: 28px; border-radius: 50%; background: var(--primary); color: #fff; display: grid; place-items: center; font-size: 10px; font-weight: 700; }
.elder-chip strong { display: block; font-size: 11px; }
.elder-chip small { display: block; margin-top: 1px; font-size: 8px; color: var(--muted); }
.service-chip { min-width: 108px; border: 1.5px solid transparent; background: #F6F5F1; border-radius: 16px; padding: 10px; text-align: left; flex-shrink: 0; }
.service-chip.active { background: #FFF8F1; border-color: var(--coral); }
.service-icon { width: 24px; height: 24px; border-radius: 8px; background: var(--soft); color: var(--primary); display: grid; place-items: center; font-size: 10px; font-weight: 700; }
.service-chip b { font-size: 10px; color: var(--coral); }
.service-chip strong { display: block; margin-top: 7px; font-size: 11px; }
.service-chip small { display: block; margin-top: 2px; font-size: 8px; color: var(--muted); }
.date-input, .time-input { border: none; background: #F2F1EC; border-radius: 999px; padding: 7px 11px; font-size: 11px; color: var(--sub); }
.selected-note { margin-top: 12px; padding: 8px 12px; border-radius: 12px; background: #EBF5F0; color: var(--primary); font-size: 10px; }
.two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.empty-inline { margin-top: 12px; padding: 16px; border-radius: 16px; background: #F7F6F2; text-align: center; font-size: 12px; color: var(--muted); }
.deposit-card { background: #FFF8EE; border-radius: 20px; padding: 15px; margin: 12px 0; font-size: 12px; color: #9A5B20; }
.deposit-card strong { color: var(--coral); }
.deposit-card p { margin: 8px 0 0; font-size: 10px; color: #B07A4A; }
.action-price { flex: 0 0 34%; padding-left: 12px; }
.action-price small { display: block; font-size: 9px; color: var(--muted); }
.action-price strong { font-size: 18px; color: var(--coral); }
.skeleton { border-radius: 999px; background: linear-gradient(90deg, #F2F1EC, #FAF9F5, #F2F1EC); }
</style>
