<template>
  <main class="page no-tab">
    <header class="topbar">
      <button class="back" @click="router.back()">‹</button>
      <span class="topbar-title">{{ id ? '编辑长辈' : '新增长辈' }}</span>
      <span class="topbar-space"></span>
    </header>
    <div class="page-intro">
      <span class="eyebrow">PROFILE</span>
      <h1>{{ id ? '编辑长辈' : '新增长辈' }}</h1>
      <p>信息只用于服务安排，健康备注请尽量简短。</p>
    </div>

    <section class="card organic">
      <h2 class="section-title">基本信息</h2>
      <div class="field"><div class="label required">姓名</div><input v-model="form.name" class="input" placeholder="长辈姓名" /></div>
      <div class="field"><div class="label">手机号</div><input v-model="form.phone" class="input" inputmode="numeric" placeholder="长辈或家属手机" /></div>
      <div class="field">
        <div class="label required">服务区域</div>
        <select v-model.number="form.station_id" class="select">
          <option :value="null" disabled>请选择服务区域</option>
          <option v-for="station in stations" :key="station.id" :value="station.id">{{ station.name }}</option>
        </select>
        <div v-if="stations.length === 1" class="helper">当前只有一个服务区域，已默认选择。</div>
      </div>
      <div class="field"><div class="label">社区</div><input v-model="form.community" class="input" placeholder="例如 示范社区" /></div>
      <div class="field"><div class="label">地址</div><input v-model="form.address" class="input" placeholder="楼栋 / 单元 / 门牌" /></div>
    </section>

    <section class="card organic">
      <h2 class="section-title">照护备注</h2>
      <div class="field"><textarea v-model="form.health_notes" class="textarea" placeholder="高血压、行动不便、需陪同复查等（非医疗诊断）" /></div>
    </section>

    <section class="card organic">
      <h2 class="section-title">紧急联系人</h2>
      <div class="field"><div class="label">姓名</div><input v-model="form.emergency_name" class="input" placeholder="姓名" /></div>
      <div class="field"><div class="label">电话</div><input v-model="form.emergency_phone" class="input" inputmode="numeric" placeholder="电话" /></div>
    </section>

    <section class="card organic agree-card">
      <label class="agree-row">
        <input v-model="agreed" type="checkbox" />
        <span>我已获得长辈及家属授权，同意收集必要的服务信息（隐私政策见「我的」）。</span>
      </label>
    </section>

    <button class="btn btn-primary btn-block save-btn" :disabled="loading" @click="save">保存</button>
  </main>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { get, patch, post } from '../api/http'
import { showToast } from '../stores/toast'

const route = useRoute()
const router = useRouter()
const id = Number(route.params.id || 0)
const stations = ref<any[]>([])
const loading = ref(true)
const agreed = ref(false)
const form = reactive<any>({
  name: '', phone: '', address: '', community: '', health_notes: '',
  emergency_name: '', emergency_phone: '', station_id: null
})

async function load() {
  loading.value = true
  try {
    const [stationData, elder] = await Promise.all([
      get<any[]>('/stations'),
      id ? get<any>(`/elders/${id}`) : Promise.resolve(null)
    ])
    stations.value = stationData || []
    if (elder) {
      Object.assign(form, elder)
      agreed.value = true
    } else if (stations.value[0]) {
      form.station_id = stations.value[0].id
    }
  } catch (e: any) {
    showToast(e.message || '加载失败')
  } finally {
    loading.value = false
  }
}

async function save() {
  if (!form.name.trim()) { showToast('请填写长辈姓名'); return }
  if (!form.station_id) { showToast('请选择服务区域'); return }
  if (!agreed.value) { showToast('请勾选授权确认'); return }
  loading.value = true
  try {
    let elder: any
    if (id) {
      elder = await patch(`/elders/${id}`, form)
    } else {
      elder = await post('/elders', form)
      await post(`/elders/${elder.id}/consents`, { type: 'service', version: 'v1', signed_by: '家属' })
    }
    showToast('已保存')
    setTimeout(() => router.back(), 300)
  } catch (e: any) {
    showToast(e.message || '保存失败')
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.page-intro { margin: 0 2px 14px; }
.page-intro h1 { margin: 6px 0 0; font-size: 26px; }
.page-intro p { margin: 4px 0 0; font-size: 11px; color: var(--muted); }
.agree-card { padding: 14px 16px; }
.agree-row { display: flex; gap: 10px; align-items: flex-start; font-size: 11px; line-height: 1.7; color: var(--sub); }
.agree-row input { margin-top: 3px; accent-color: var(--primary); }
.save-btn { margin-top: 6px; }
</style>
