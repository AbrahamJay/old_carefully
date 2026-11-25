<template>
  <main class="page no-tab staff-record-page" :class="{ 'with-action': isAssigned || isInService }">
    <header class="topbar">
      <button class="back" @click="router.back()">‹</button>
      <span class="topbar-title">服务订单</span>
      <span class="topbar-space"></span>
    </header>

    <div v-if="loading && !order" class="card"><div class="skeleton" style="height: 22px; width: 45%"></div></div>
    <template v-else-if="order">
      <section class="card organic record-hero">
        <div class="row between">
          <div><span class="eyebrow">SERVICE ORDER</span><h1>{{ order.service?.name }}</h1></div>
          <span class="tag" :class="statusCls">{{ statusText }}</span>
        </div>
        <div class="divider"></div>
        <div class="info-row"><span class="info-key">服务对象</span><span class="info-value">{{ order.elder?.name }}</span></div>
        <div class="info-row"><span class="info-key">时间</span><span class="info-value">{{ timeText }}</span></div>
        <div class="info-row"><span class="info-key">地址</span><span class="info-value">{{ order.address }}</span></div>
        <div class="info-row"><span class="info-key">联系人</span><span class="info-value">{{ order.contact_name }} {{ order.contact_phone }}</span></div>
        <div v-if="order.notes" class="info-block"><span class="info-key">备注</span><div class="info-text">{{ order.notes }}</div></div>
      </section>

      <section v-if="isAssigned" class="card organic warm">
        <h2 class="section-title">下一步</h2>
        <p class="small muted mt8">接单并开始服务后，才能提交服务记录。</p>
      </section>

      <section v-if="isInService" class="card organic">
        <h2 class="section-title">服务记录</h2>
        <p class="small muted mt8">记录服务内容或上传 1–3 张照片（至少一项），提交后完成订单。</p>
        <textarea v-model="content" class="textarea mt12" placeholder="例如：陪同完成复查，医嘱已拍照发给家属；代取药 2 盒。" />
        <div class="photo-grid mt12">
          <div v-for="(photo, index) in photos" :key="photo.path" class="photo-item">
            <img :src="photo.url" alt="服务照片" @click="preview(photo.url)" />
            <button class="remove" @click="removePhoto(index)">×</button>
          </div>
          <label v-if="canAddPhoto" class="photo-add">
            +<input type="file" accept="image/*" capture="environment" @change="chooseImage" />
          </label>
        </div>
        <div class="helper">照片仅用于服务留痕，不会对外公开。</div>
      </section>

      <section v-if="isCompleted" class="card organic">
        <h2 class="section-title">已完成</h2>
        <p class="small muted mt8">这单已经完成，以下是你提交的服务记录。</p>
      </section>

      <section v-if="order.records?.length" class="card organic">
        <h2 class="section-title">已提交的服务记录（{{ order.records.length }}）</h2>
        <div v-for="record in orderRecords" :key="record.id" class="record">
          <div class="row between">
            <span class="record-time">{{ record.timeText }}</span>
            <span class="tag" :class="record.elder_confirmed ? 'tag-completed' : 'tag-pending'">{{ record.elder_confirmed ? '家属已确认' : '待家属确认' }}</span>
          </div>
          <p>{{ record.content }}</p>
          <div v-if="record.photos?.length" class="photo-grid mt12">
            <img v-for="photo in record.photos" :key="photo" :src="photo" alt="服务记录" @click="preview(photo)" />
          </div>
        </div>
      </section>
    </template>

    <div v-if="order && (isAssigned || isInService)" class="action-bar">
      <button v-if="isAssigned" class="btn btn-primary" @click="acceptAndStart">接单并开始</button>
      <button v-if="isInService" class="btn btn-primary" :disabled="submitting" @click="submit">{{ submitting ? '提交中...' : '提交记录并完成' }}</button>
    </div>
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { get, post, upload } from '../api/http'
import { dateTime, statusInfo } from '../api/format'
import { showToast } from '../stores/toast'

const route = useRoute()
const router = useRouter()
const id = Number(route.params.id)
const order = ref<any>(null)
const loading = ref(true)
const content = ref('')
const photos = ref<{ path: string; url: string }[]>([])
const submitting = ref(false)

const statusCls = computed(() => order.value ? statusInfo(order.value.status).cls : '')
const statusText = computed(() => {
  if (!order.value) return ''
  if (order.value.status === 'assigned') return '待接单'
  if (order.value.status === 'in_service') return '服务中'
  if (order.value.status === 'completed') return '服务已完成'
  return statusInfo(order.value.status).text
})
const timeText = computed(() => dateTime(order.value?.scheduled_at))
const isAssigned = computed(() => order.value?.status === 'assigned')
const isInService = computed(() => order.value?.status === 'in_service')
const isCompleted = computed(() => order.value?.status === 'completed')
const canAddPhoto = computed(() => photos.value.length < 3)
const orderRecords = computed(() => (order.value?.records || []).map((record: any) => ({
  ...record,
  timeText: dateTime(record.checkin_at)
})))

async function load() {
  loading.value = true
  try {
    order.value = await get(`/orders/${id}`)
  } catch (e: any) {
    showToast(e.message || '加载失败')
  } finally {
    loading.value = false
  }
}

async function acceptAndStart() {
  try {
    await post(`/orders/${id}/accept`)
    await post(`/orders/${id}/start`)
    showToast('已开始服务')
    await load()
  } catch (e: any) {
    showToast(e.message || '操作失败')
  }
}

async function chooseImage(event: Event) {
  const input = event.target as HTMLInputElement
  const files = Array.from(input.files || []).slice(0, 3 - photos.value.length)
  input.value = ''
  for (const file of files) {
    try {
      const data = await upload(file)
      photos.value.push({ path: data.url, url: data.url })
    } catch (e: any) {
      showToast(e.message || '上传失败')
    }
  }
}

function removePhoto(index: number) {
  photos.value.splice(index, 1)
}

function preview(url: string) {
  window.open(url, '_blank')
}

async function submit() {
  if (!content.value.trim() && !photos.value.length) {
    showToast('写两句或上传照片')
    return
  }
  submitting.value = true
  try {
    await post(`/orders/${id}/records`, {
      content: content.value || '已上传服务照片',
      photos: photos.value.map(item => item.path),
      elder_confirmed: false
    })
    await post(`/orders/${id}/complete`)
    showToast('已完成')
    content.value = ''
    photos.value = []
    await load()
  } catch (e: any) {
    showToast(e.message || '提交失败')
  } finally {
    submitting.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.staff-record-page { padding: 22px 18px 32px; }
.record-hero h1 { margin: 6px 0 0; font-size: 26px; }
.info-row { display: flex; justify-content: space-between; gap: 14px; padding: 4px 0; font-size: 12px; }
.info-key { color: var(--muted); flex-shrink: 0; }
.info-value { text-align: right; }
.info-block { margin-top: 10px; }
.info-text { margin-top: 4px; font-size: 12px; line-height: 1.7; }
.photo-grid { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 10px; }
.photo-grid img { width: 88px; height: 88px; object-fit: cover; border-radius: 14px; }
.photo-item { position: relative; }
.remove { position: absolute; top: -7px; right: -7px; width: 22px; height: 22px; border: none; border-radius: 50%; background: rgba(26,36,32,.75); color: #fff; font-size: 14px; }
.photo-add { width: 88px; height: 88px; display: grid; place-items: center; border-radius: 14px; background: #F5F4F0; color: var(--muted); font-size: 26px; }
.photo-add input { display: none; }
.record { padding: 12px 0; border-bottom: 1px solid var(--line); }
.record:last-child { border-bottom: none; }
.record-time { font-size: 10px; color: var(--muted); }
.record p { margin: 6px 0 0; font-size: 13px; line-height: 1.7; }
.skeleton { border-radius: 999px; background: linear-gradient(90deg, #F2F1EC, #FAF9F5, #F2F1EC); }
</style>
