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
        <div v-if="chatEnabled" class="chat-entry">
          <button class="btn btn-ghost" @click="openChat">问问这单</button>
          <span class="helper">只回答这一单的事，不会替你操作</span>
        </div>
      </section>

      <section v-if="prepItems.length" class="card organic warm">
        <div class="row between">
          <h2 class="section-title">服务前提示</h2>
          <span class="eyebrow">AI</span>
        </div>
        <ul class="ai-list">
          <li v-for="item in prepItems" :key="item">{{ item }}</li>
        </ul>
      </section>

      <section v-if="isAssigned" class="card organic warm">
        <h2 class="section-title">下一步</h2>
        <p class="small muted mt8">接单并开始服务后，才能提交服务记录。</p>
      </section>

      <section v-if="isInService" class="card organic">
        <h2 class="section-title">服务记录</h2>
        <p class="small muted mt8">记录服务内容或上传 1–3 张照片（至少一项），提交后完成订单。</p>
        <!-- AI 润色嵌在输入框里：只保留一个框，写完直接在框里点右下角 -->
        <div class="textarea-wrap mt12">
          <textarea
            v-model="content"
            class="textarea"
            :class="{ 'with-ai': agentEnabled }"
            placeholder="例如：陪同完成复查，医嘱已拍照发给家属；代取药 2 盒。"
            @input="polishedFrom = ''"
          />
          <button
            v-if="agentEnabled"
            type="button"
            class="ai-inline"
            :disabled="agentBusy || !content.trim()"
            @click="polishContent"
          >
            {{ agentBusy ? '润色中' : 'AI 润色' }}
          </button>
        </div>
        <p v-if="agentEnabled" class="ai-hint">
          <span>AI 只润色文字，不改事实、不会自动提交</span>
          <button v-if="polishedFrom" type="button" @click="undoPolish">已润色 · 撤销</button>
        </p>
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

    <div v-if="chatOpen" class="chat-mask" @click.self="closeChat">
      <section class="chat-sheet">
        <div class="row between">
          <div><span class="eyebrow">AI</span><h2 class="section-title">问问这单</h2></div>
          <button class="chat-close" aria-label="关闭" @click="closeChat">×</button>
        </div>
        <div ref="chatListRef" class="chat-list">
          <p v-if="!chatMessages.length" class="helper">
            可以问：几点到、老人有什么要注意、记录怎么写。退款、改派、投诉请找站点管家。
          </p>
          <div v-for="(item, index) in chatMessages" :key="index" class="chat-item" :class="item.role">
            <div class="chat-text">{{ item.content || '…' }}</div>
          </div>
          <p v-if="chatNote" class="chat-note">{{ chatNote }}</p>
        </div>
        <div class="chat-input">
          <textarea
            v-model="chatInput"
            class="textarea"
            maxlength="200"
            rows="2"
            placeholder="例如：老人有什么要注意"
            @keyup.enter.exact.prevent="sendChat"
          />
          <button class="btn btn-primary" :disabled="chatBusy || !chatInput.trim()" @click="sendChat">
            {{ chatBusy ? '回答中...' : '发送' }}
          </button>
        </div>
        <div class="helper">AI 只整理订单里已有的事实；数字有出入请以订单为准。</div>
      </section>
    </div>
  </main>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { get, post, upload } from '../api/http'
import { chatStream, type ChatMessage } from '../api/agent'
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
// AI 只是可选辅助：开关关闭、额度用尽或服务异常时，手工填写必须照常可用
const agentEnabled = ref(false)
const prepItems = ref<string[]>([])
const agentBusy = ref(false)
// 润色会覆盖输入框原文，留一份用于撤销；员工手动编辑后自动失效
const polishedFrom = ref('')
// 对话（阶段七）：同一套开关，但额度与写记录分开
const chatEnabled = ref(false)
const chatOpen = ref(false)
const chatBusy = ref(false)
const chatInput = ref('')
const chatMessages = ref<ChatMessage[]>([])
const chatNote = ref('')
const chatListRef = ref<HTMLElement | null>(null)

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
    polishedFrom.value = ''
    photos.value = []
    await load()
  } catch (e: any) {
    showToast(e.message || '提交失败')
  } finally {
    submitting.value = false
  }
}

onMounted(async () => {
  await load()
  await initAgent()
})

async function initAgent() {
  try {
    const status = await get('/agent/status')
    agentEnabled.value = !!status.enabled
    chatEnabled.value = !!(status.enabled && status.chat_enabled)
    if (!agentEnabled.value) return
    if (isAssigned.value || isInService.value) await loadPrepBrief()
  } catch {
    // 状态接口失败时静默降级，不打扰员工
    agentEnabled.value = false
  }
}

async function loadPrepBrief() {
  try {
    const data = await post('/agent/staff/prep-brief', { order_id: id })
    prepItems.value = data.items || []
  } catch {
    prepItems.value = []
  }
}

function warningText(code: string) {
  const map: Record<string, string> = {
    redline: '检测到紧急情况，请先联系家属与站点，再手工记录',
    bad_output: 'AI 输出未能解析，请手工补充',
    empty_content: 'AI 内容为空，请补充要点后重试',
    truncated: '内容过长已截断，请核对',
    medical_guard: '已移除涉及用药建议的表述，请核对'
  }
  if (code.startsWith('missing_section:')) return `缺少「${code.split(':')[1]}」，请补充`
  return map[code] || ''
}

async function polishContent() {
  // 直接润色输入框里的文字：空内容不允许调用，也不花钱
  const text = content.value.trim()
  if (!text || agentBusy.value) return
  // 后端 rough_notes 限 500 字：先在前端拦住，不然员工看到的是校验报错原文
  if (text.length > 500) {
    showToast('超过 500 字，先精简再润色')
    return
  }
  agentBusy.value = true
  try {
    const data = await post('/agent/staff/record-draft', {
      order_id: id,
      rough_notes: text,
      photo_count: photos.value.length
    })
    if (!data.content) {
      showToast('润色结果为空，已保留你写的内容')
      return
    }
    polishedFrom.value = content.value
    content.value = data.content
    const warnings: string[] = data.warnings || []
    const tip = warnings.map(warningText).find(Boolean)
    showToast(tip || '已润色，请核对后提交')
  } catch (e: any) {
    // 失败不改原文：宁可没润色，也不能把员工写好的内容弄丢
    showToast(e.message || '润色失败，内容未改动')
  } finally {
    agentBusy.value = false
  }
}

function undoPolish() {
  if (!polishedFrom.value) return
  content.value = polishedFrom.value
  polishedFrom.value = ''
}

// ------------------------------------------------------ 「这单助手」对话
const chatWarningText: Record<string, string> = {
  redline: '已按急症流程给固定指引，请先联系家属与站点',
  out_of_scope: '这类操作需要站点管家处理',
  chat_guard: '已移除涉及用药建议的表述',
  chat_number_guard: '回答里的数字请以订单为准',
  chat_truncated: '回答过长已截断'
}

function scrollChat() {
  nextTick(() => {
    if (chatListRef.value) chatListRef.value.scrollTop = chatListRef.value.scrollHeight
  })
}

function openChat() {
  chatOpen.value = true
  scrollChat()
}

function closeChat() {
  chatOpen.value = false
}

async function sendChat() {
  const question = chatInput.value.trim()
  if (!question || chatBusy.value) return
  // 只带最近 6 条：服务端还会按配置再裁一次，不把整段聊天塞进 prompt
  const history = chatMessages.value.slice(-6).map(item => ({ ...item }))
  chatMessages.value.push({ role: 'user', content: question })
  chatMessages.value.push({ role: 'assistant', content: '' })
  chatInput.value = ''
  chatNote.value = ''
  chatBusy.value = true
  scrollChat()
  try {
    const result = await chatStream(id, question, history, (text) => {
      const last = chatMessages.value[chatMessages.value.length - 1]
      last.content += text
      scrollChat()
    })
    // 用服务端的最终文本兜底：流被截断时前端也不会只留半句
    chatMessages.value[chatMessages.value.length - 1].content =
      result.answer || 'AI 这次没生成内容，可以再问一次，或直接看上面的订单信息。'
    chatNote.value = (result.warnings || []).map(code => chatWarningText[code]).find(Boolean) || ''
  } catch (e: any) {
    // 请求失败时不需要保留占位的空回答
    chatMessages.value.splice(-2)
    chatMessages.value.push({ role: 'user', content: question })
    chatMessages.value.push({
      role: 'assistant',
      content: e.message || 'AI 暂时不可用，可先看订单信息或联系站点管家'
    })
    showToast(e.message || 'AI 暂时不可用')
  } finally {
    chatBusy.value = false
    scrollChat()
  }
}
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
.ai-list { margin: 10px 0 0; padding-left: 18px; font-size: 13px; line-height: 1.8; }
.textarea-wrap { position: relative; }
/* 给右下角的按钮让位，避免长长的第二行被盖住 */
.textarea.with-ai { padding-bottom: 46px; }
.ai-inline {
  position: absolute;
  right: 10px;
  bottom: 10px;
  height: 30px;
  padding: 0 12px;
  border: none;
  border-radius: 999px;
  background: #EDF4F0;
  color: var(--primary);
  font-size: 12px;
  font-weight: 600;
}
.ai-inline:disabled { opacity: .45; }
.ai-hint { display: flex; justify-content: space-between; gap: 8px; margin: 7px 0 0; font-size: 10px; color: var(--muted); }
.ai-hint button { border: none; background: none; padding: 0; font-size: 10px; color: var(--primary); text-decoration: underline; }
.chat-entry { margin-top: 12px; display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.chat-mask { position: fixed; inset: 0; background: rgba(26, 36, 32, .45); display: flex; align-items: flex-end; z-index: 30; }
.chat-sheet { width: 100%; max-height: 82vh; padding: 16px 18px 22px; display: flex; flex-direction: column; gap: 10px; background: #FBFAF6; border-radius: 22px 22px 0 0; }
.chat-close { border: none; background: none; font-size: 22px; line-height: 1; color: var(--muted); }
.chat-list { flex: 1; min-height: 140px; overflow-y: auto; display: flex; flex-direction: column; gap: 8px; }
.chat-item { display: flex; }
.chat-item.user { justify-content: flex-end; }
.chat-text { max-width: 84%; padding: 9px 12px; border-radius: 14px; font-size: 13px; line-height: 1.65; background: #F1F0EA; white-space: pre-wrap; }
.chat-item.user .chat-text { background: #1A2420; color: #fff; }
.chat-note { margin: 0; font-size: 11px; color: #B4690E; }
.chat-input { display: flex; gap: 8px; align-items: flex-end; }
.chat-input .textarea { flex: 1; }
.skeleton { border-radius: 999px; background: linear-gradient(90deg, #F2F1EC, #FAF9F5, #F2F1EC); }
</style>
