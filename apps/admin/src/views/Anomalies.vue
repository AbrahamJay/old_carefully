<template>
  <div>
    <div class="page-head">
      <div>
        <div class="page-title">异常巡检</div>
        <div class="page-sub">定时扫描六大类异常，只提示不自动处理；处理动作全部留痕</div>
      </div>
      <div class="head-actions">
        <el-button :loading="scanning" @click="runScan">立即扫描</el-button>
        <el-button @click="refreshAll">刷新</el-button>
      </div>
    </div>

    <el-alert
      v-if="!summary.scan_enabled"
      class="off-alert"
      type="warning"
      :closable="false"
      show-icon
      title="异常巡检已关闭"
      description="ANOMALY_SCAN_ENABLED=false：worker 不会扫描，队列保持现状；打开后重启 worker 即可恢复。"
    />

    <div class="stat-grid">
      <div class="stat-card">
        <div class="stat-label">待处理</div>
        <div class="stat-value orange">{{ summary.open }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">高优先级</div>
        <div class="stat-value orange">{{ summary.high }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">今日已处理</div>
        <div class="stat-value green">{{ summary.handled_today }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">平均处理时长</div>
        <div class="stat-value green">{{ summary.avg_handle_minutes }}<span class="unit">分钟</span></div>
      </div>
    </div>

    <div class="scan-line">
      每 {{ summary.scan_interval_minutes }} 分钟扫描一次 · 最近扫描 {{ lastScanText }}
      <span v-if="!summary.last_scan_at" class="muted">（还没有扫描记录，可先点「立即扫描」）</span>
    </div>

    <div class="workbench">
      <aside class="queue page-card">
        <div class="queue-head">
          <span>异常队列</span>
          <el-tag :type="list.length ? 'warning' : 'info'" round>{{ total }}</el-tag>
        </div>
        <div class="filters">
          <el-select v-model="statusFilter" style="width: 100%" @change="reloadList">
            <el-option label="待处理" value="open" />
            <el-option label="已稍后" value="snoozed" />
            <el-option label="已处理" value="handled" />
            <el-option label="已忽略" value="ignored" />
            <el-option label="已自动收敛" value="resolved" />
            <el-option label="全部状态" value="" />
          </el-select>
          <el-select v-model="typeFilter" style="width: 100%" @change="reloadList">
            <el-option label="全部类型" value="" />
            <el-option v-for="item in TYPES" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
        </div>

        <el-empty v-if="!list.length" description="队列为空，状态很好" :image-size="72" />
        <button
          v-for="item in list"
          :key="item.id"
          class="queue-item"
          :class="{ active: String(item.id) === taskId }"
          @click="selectTask(item.id)"
        >
          <div class="queue-row">
            <el-tag :type="severityType(item.severity)" size="small">{{ severityText(item.severity) }}</el-tag>
            <el-tag size="small" effect="plain">{{ typeText(item.type) }}</el-tag>
            <span v-if="item.status !== 'open'" class="queue-status">{{ statusText(item.status) }}</span>
          </div>
          <div class="queue-main">{{ item.title }}</div>
          <div class="queue-sub">
            {{ item.elder_name }} · {{ item.service_name }} · 等待 {{ waitedText(item.detected_at) }}
          </div>
        </button>
      </aside>

      <section v-if="current" class="detail">
        <div class="page-card">
          <div class="detail-head">
            <div>
              <div class="detail-title">{{ current.title }}</div>
              <div class="page-sub">
                {{ typeText(current.type) }} · 识别于 {{ formatTime(current.detected_at) }}
                <span v-if="current.status === 'snoozed'"> · 稍后到 {{ formatTime(current.snoozed_until) }}</span>
              </div>
            </div>
            <div class="tag-row">
              <el-tag :type="severityType(current.severity)">{{ severityText(current.severity) }}</el-tag>
              <el-tag :type="current.status === 'open' ? 'warning' : 'info'">{{ statusText(current.status) }}</el-tag>
            </div>
          </div>

          <el-descriptions :column="2" border>
            <el-descriptions-item label="老人">{{ current.elder_name || facts.elder_name || '—' }}</el-descriptions-item>
            <el-descriptions-item label="服务">{{ current.service_name || facts.service_name || '—' }}</el-descriptions-item>
            <el-descriptions-item label="预约时间">{{ formatTime(current.scheduled_at || facts.scheduled_at) }}</el-descriptions-item>
            <el-descriptions-item label="服务区域">{{ current.station_name || facts.station_name || '未分配' }}</el-descriptions-item>
            <el-descriptions-item label="社区">{{ facts.community || '未维护' }}</el-descriptions-item>
            <el-descriptions-item label="服务人员">{{ facts.staff_name || '未派单' }}</el-descriptions-item>
            <el-descriptions-item label="上门地址" :span="2">{{ facts.address || '—' }}</el-descriptions-item>
            <el-descriptions-item label="订单状态">{{ orderStatusText(current.order_status || facts.order_status) }}</el-descriptions-item>
            <el-descriptions-item label="收款">
              {{ payText(facts.payment_status) }}
              <span v-if="facts.remaining_cents"> · 待收 ¥{{ money(facts.remaining_cents) }}</span>
            </el-descriptions-item>
          </el-descriptions>

          <div class="actions">
            <el-button @click="goOrder">去处理这一单</el-button>
            <template v-if="isActive">
              <el-button @click="openSnooze">稍后处理</el-button>
              <el-button type="primary" @click="markHandled">标记已处理</el-button>
              <el-button type="danger" plain @click="markIgnored">忽略</el-button>
            </template>
          </div>

          <div v-if="!isActive" class="closed-hint">
            该任务已结束：{{ statusText(current.status) }}
            <span v-if="current.note"> · {{ current.note }}</span>
            <span v-if="current.handled_at"> · 处理于 {{ formatTime(current.handled_at) }}</span>
          </div>
        </div>

        <div class="page-card">
          <div class="block-head">
            <div class="block-title">规则解释</div>
            <el-button
              v-if="aiOn && isActive"
              size="small"
              type="primary"
              plain
              :loading="aiLoading"
              @click="loadAi(false)"
            >
              AI 解释
            </el-button>
          </div>
          <div class="explain-row">
            <span class="explain-label">为什么被标记</span>
            <p>{{ facts.why || '—' }}</p>
          </div>
          <div class="explain-row">
            <span class="explain-label">建议先做什么</span>
            <p>{{ facts.suggest || '—' }}</p>
          </div>
          <div class="rule-line">
            <span class="explain-label">触发规则</span>
            <code>{{ facts.rule || '—' }}</code>
          </div>
          <div class="rule-meta">
            阈值 {{ thresholdText }} · 已等待 {{ facts.elapsed_minutes ?? 0 }} 分钟
          </div>
          <div class="explain-note">
            以上解释由扫描规则直接生成；AI 解释只换一种说法，不改变事实与判定。
          </div>

          <div v-if="aiData" class="ai-block">
            <div class="ai-head">
              <el-tag :type="aiSourceType" size="small" round>{{ aiSourceText }}</el-tag>
              <span class="muted">{{ aiData.model || '规则引擎' }} · {{ aiData.latency_ms }}ms</span>
              <el-button size="small" text :loading="aiLoading" @click="loadAi(true)">重新生成</el-button>
            </div>
            <el-alert
              v-if="aiData.source === 'rule'"
              type="info"
              :closable="false"
              show-icon
              title="本次为规则文案"
              description="AI 暂不可用或输出未通过校验，以下内容直接取自扫描规则。"
            />
            <el-alert
              v-if="aiData.escalate"
              type="warning"
              :closable="false"
              show-icon
              title="建议升级处理"
              description="已多次超时或影响较大，请尽快联系相关方并在处理后填写说明。"
            />
            <div class="ai-summary">{{ aiData.what_happened || '—' }}</div>
            <div class="ai-line">
              <span class="explain-label">原因</span>
              <p>{{ aiData.why || '—' }}</p>
            </div>
            <div class="ai-actions">
              <span class="explain-label">建议动作</span>
              <div class="ai-tags">
                <el-tag
                  v-for="item in aiData.next_actions"
                  :key="item.action"
                  type="success"
                  effect="plain"
                  size="small"
                >
                  {{ item.label }}
                </el-tag>
              </div>
            </div>
            <div v-if="aiData.data_gaps.length" class="ai-line">
              <span class="explain-label">补充信息</span>
              <p>{{ aiData.data_gaps.join('；') }}</p>
            </div>
            <div class="explain-note">AI 只整理已有事实，不会自动处理；处理动作仍需点击上方按钮并留痕。</div>
          </div>
        </div>
      </section>

      <section v-else class="page-card empty-detail">
        <el-empty description="从左侧队列选择一条异常" :image-size="96" />
      </section>
    </div>

    <el-dialog v-model="snoozeVisible" title="稍后处理" width="420px">
      <el-radio-group v-model="snoozeHours">
        <el-radio-button :value="1">1 小时</el-radio-button>
        <el-radio-button :value="2">2 小时</el-radio-button>
        <el-radio-button :value="4">4 小时</el-radio-button>
        <el-radio-button :value="24">明天</el-radio-button>
      </el-radio-group>
      <el-input v-model="snoozeNote" placeholder="可选备注（会记录下来）" class="snooze-note" />
      <div class="muted">到期后如果异常仍然存在，会重新回到待处理队列。</div>
      <template #footer>
        <el-button @click="snoozeVisible = false">取消</el-button>
        <el-button type="primary" @click="confirmSnooze">确定稍后</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { request, agentStatus, taskExplain } from '../api'
import type { TaskExplain } from '../api'

const TYPES = [
  { value: 'pending_timeout', label: '待确认超时' },
  { value: 'confirmed_unassigned', label: '已确认未派' },
  { value: 'assigned_not_accepted', label: '已派未接' },
  { value: 'in_service_overrun', label: '服务中超时' },
  { value: 'balance_due', label: '尾款未结' },
  { value: 'missing_record', label: '缺服务记录' }
]
const TYPE_LABEL: Record<string, string> = Object.fromEntries(TYPES.map((item) => [item.value, item.label]))
const STATUS_LABEL: Record<string, string> = {
  open: '待处理', snoozed: '已稍后', handled: '已处理', ignored: '已忽略', resolved: '已自动收敛'
}
const ORDER_STATUS: Record<string, string> = {
  pending_confirm: '待确认', confirmed: '待派单', assigned: '已派单', in_service: '服务中',
  completed: '已完成', cancelled: '已取消'
}
const PAY: Record<string, string> = {
  unpaid: '未收款', deposit_paid: '已付定金', paid_offline: '已收款', paid_mock: '已收款', refunded: '已退款'
}

const route = useRoute()
const router = useRouter()

const summary = ref<any>({
  open: 0, high: 0, handled_today: 0, avg_handle_minutes: 0,
  scan_interval_minutes: 10, scan_enabled: true, last_scan_at: null, by_type: {}
})
const list = ref<any[]>([])
const total = ref(0)
const statusFilter = ref('open')
const typeFilter = ref('')
const current = ref<any>(null)
const scanning = ref(false)
const snoozeVisible = ref(false)
const snoozeHours = ref(2)
const snoozeNote = ref('')
// AI 解释：后端已做脱敏与白名单，前端只负责条件展示
const aiOn = ref(false)
const aiLoading = ref(false)
const aiData = ref<TaskExplain | null>(null)

const taskId = computed(() => (route.query.task ? String(route.query.task) : ''))
const facts = computed(() => current.value?.detail || {})
const isActive = computed(
  () => !!current.value && ['open', 'snoozed'].includes(current.value.status)
)
const lastScanText = computed(() => formatTime(summary.value.last_scan_at) || '—')
const aiSourceText = computed(() => {
  const source = aiData.value?.source
  if (source === 'llm') return 'AI 解释'
  if (source === 'cache') return '缓存结果'
  return '规则文案'
})
const aiSourceType = computed(() => {
  const source = aiData.value?.source
  if (source === 'llm') return 'success'
  if (source === 'cache') return 'info'
  return 'warning'
})
const thresholdText = computed(() => {
  const minutes = Number(facts.value.threshold_minutes || 0)
  if (!minutes) return '立即命中'
  if (minutes >= 60 && minutes % 60 === 0) return `${minutes / 60} 小时`
  if (minutes > 60) return `${(minutes / 60).toFixed(1)} 小时`
  return `${minutes} 分钟`
})

function typeText(value: string) { return TYPE_LABEL[value] || value || '—' }
function statusText(value: string) { return STATUS_LABEL[value] || value || '—' }
function severityText(value: string) { return { high: '高', medium: '中', low: '低' }[value] || value }
function severityType(value: string) {
  if (value === 'high') return 'danger'
  if (value === 'medium') return 'warning'
  return 'info'
}
function orderStatusText(value: string) { return ORDER_STATUS[value] || value || '—' }
function payText(value: string) { return PAY[value] || value || '—' }
function money(cents: number) { return ((cents || 0) / 100).toFixed(2).replace('.00', '') }
function formatTime(value: string) { return value ? value.replace('T', ' ').slice(0, 16) : '' }
function waitedText(value: string) {
  if (!value) return '—'
  const minutes = Math.max(0, Math.floor((Date.now() - new Date(value).getTime()) / 60000))
  if (minutes < 60) return `${minutes} 分钟`
  if (minutes < 60 * 24) return `${(minutes / 60).toFixed(1)} 小时`
  return `${(minutes / 1440).toFixed(1)} 天`
}

function notifyLayout() {
  window.dispatchEvent(new Event('anomaly:refresh'))
}

async function loadAgentStatus() {
  try {
    const status = await agentStatus()
    aiOn.value = status.enabled && (status.admin_scenarios || []).includes('task_explain')
  } catch {
    // 状态拿不到就不显示入口，不影响异常处理主流程
    aiOn.value = false
  }
}

async function loadAi(force = false) {
  if (!current.value || aiLoading.value) return
  aiLoading.value = true
  try {
    aiData.value = await taskExplain(current.value.id, force)
  } catch (error: any) {
    ElMessage.error(error.message)
  } finally {
    aiLoading.value = false
  }
}

async function loadSummary() {
  try {
    summary.value = await request('/admin/tasks/summary')
  } catch {
    // 概览失败不阻断队列；登录过期由 request 统一处理
  }
}

async function loadList() {
  const params = new URLSearchParams({ page_size: '100' })
  if (statusFilter.value) params.set('status', statusFilter.value)
  if (typeFilter.value) params.set('type', typeFilter.value)
  const data = await request('/admin/tasks?' + params.toString())
  list.value = data.items || []
  total.value = data.total || 0
}

async function loadDetail(id: number) {
  // 换任务后旧的解释不再适用
  aiData.value = null
  const inList = list.value.find((item) => item.id === id)
  if (inList) {
    current.value = inList
    return
  }
  try {
    current.value = await request('/admin/tasks/' + id)
  } catch (error: any) {
    current.value = null
    ElMessage.error(error.message)
  }
}

async function reloadList() {
  await loadList()
  if (taskId.value && list.value.some((item) => String(item.id) === taskId.value)) {
    await loadDetail(Number(taskId.value))
  }
  notifyLayout()
}

function selectTask(id: number) {
  router.replace({ path: '/anomalies', query: { task: String(id) } })
}

async function refreshAll() {
  await Promise.all([loadSummary(), loadList()])
  notifyLayout()
  if (taskId.value) {
    if (list.value.some((item) => String(item.id) === taskId.value)) {
      await loadDetail(Number(taskId.value))
    } else if (list.value.length) {
      selectTask(list.value[0].id)
    } else {
      current.value = null
      router.replace({ path: '/anomalies' })
    }
  } else if (list.value.length) {
    selectTask(list.value[0].id)
  }
}

async function runScan() {
  scanning.value = true
  try {
    const result = await request('/admin/tasks/scan', { method: 'POST' })
    if (!result.scanned) {
      ElMessage.info(result.skip_reason || '本轮扫描已跳过')
    } else {
      ElMessage.success(
        `扫描完成：命中 ${result.detected} 条，新增 ${result.created}，自动收敛 ${result.resolved}`
      )
    }
    await refreshAll()
  } catch (error: any) {
    ElMessage.error(error.message)
  } finally {
    scanning.value = false
  }
}

function goOrder() {
  if (!current.value?.order_no) return
  router.push({ path: '/orders', query: { keyword: current.value.order_no } })
}

function openSnooze() {
  snoozeHours.value = 2
  snoozeNote.value = ''
  snoozeVisible.value = true
}

async function confirmSnooze() {
  if (!current.value) return
  try {
    await request(`/admin/tasks/${current.value.id}/snooze`, {
      method: 'POST',
      body: { hours: snoozeHours.value, note: snoozeNote.value }
    })
    snoozeVisible.value = false
    ElMessage.success(`已稍后 ${snoozeHours.value} 小时，到期会重新出现`)
    await refreshAll()
  } catch (error: any) {
    ElMessage.error(error.message)
  }
}

async function markHandled() {
  if (!current.value) return
  try {
    const result: any = await ElMessageBox.prompt(
      '处理说明会连同操作人和时间一起记录。',
      '标记已处理',
      {
        inputPlaceholder: '例如：已电话联系家属，改约到明日上午',
        inputValidator: (value: string) => (!!value && !!value.trim()) || '请填写处理说明',
        type: 'warning'
      }
    )
    await request(`/admin/tasks/${current.value.id}/handle`, {
      method: 'POST',
      body: { note: String(result.value || '').trim() }
    })
    ElMessage.success('已标记处理')
    await refreshAll()
  } catch (error: any) {
    if (error !== 'cancel' && error !== 'close') ElMessage.error(error?.message || '操作失败')
  }
}

async function markIgnored() {
  if (!current.value) return
  try {
    const result: any = await ElMessageBox.prompt(
      '忽略原因会记录下来，条件消失前不再提示。',
      '忽略这条异常',
      {
        inputPlaceholder: '例如：家属已自行联系员工，无需干预',
        inputValidator: (value: string) => (!!value && !!value.trim()) || '请填写忽略原因',
        type: 'warning'
      }
    )
    await request(`/admin/tasks/${current.value.id}/ignore`, {
      method: 'POST',
      body: { reason: String(result.value || '').trim() }
    })
    ElMessage.success('已忽略')
    await refreshAll()
  } catch (error: any) {
    if (error !== 'cancel' && error !== 'close') ElMessage.error(error?.message || '操作失败')
  }
}

watch(
  () => route.query.task,
  (value) => {
    if (value) {
      loadDetail(Number(value))
    } else {
      current.value = null
    }
  },
  { immediate: true }
)

onMounted(async () => {
  await refreshAll()
  loadAgentStatus()
})
</script>

<style scoped>
.head-actions { display: flex; gap: 8px; }
.off-alert { margin-bottom: 16px; border-radius: 16px; }
.unit { font-size: 13px; font-weight: 600; margin-left: 4px; color: var(--text-tertiary, #8C9690); }
.scan-line { margin-top: 14px; font-size: 12px; color: #8C9690; }
.muted { color: #8C9690; font-size: 12px; }

.workbench {
  display: grid;
  grid-template-columns: 340px minmax(0, 1fr);
  gap: 16px;
  align-items: start;
  margin-top: 16px;
}
.queue {
  padding: 14px;
  max-height: calc(100vh - 260px);
  overflow: auto;
  position: sticky;
  top: 18px;
}
.queue-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 4px 6px 12px;
  font-size: 14px;
  font-weight: 700;
  color: #1A2420;
}
.filters { display: flex; flex-direction: column; gap: 8px; padding: 0 2px 12px; }
.queue-item {
  width: 100%;
  text-align: left;
  border: none;
  background: #F7F6F2;
  border-radius: 16px;
  padding: 12px 14px;
  margin-bottom: 10px;
  cursor: pointer;
  transition: background 0.15s ease, box-shadow 0.15s ease;
}
.queue-item:hover { background: #F1EEE7; }
.queue-item.active { background: #EAF2EC; box-shadow: inset 0 0 0 1px #1F6345; }
.queue-row { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.queue-status { margin-left: auto; font-size: 11px; color: #8C9690; }
.queue-main { margin-top: 8px; font-size: 14px; font-weight: 600; color: #1A2420; }
.queue-sub { margin-top: 4px; font-size: 12px; color: #8C9690; }

.detail { display: flex; flex-direction: column; gap: 16px; min-width: 0; }
.detail-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; margin-bottom: 16px; }
.detail-title { font-size: 18px; font-weight: 700; color: #1A2420; }
.tag-row { display: flex; gap: 6px; flex-shrink: 0; }
.actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 18px; flex-wrap: wrap; }
.closed-hint {
  margin-top: 16px;
  padding: 12px 14px;
  border-radius: 14px;
  background: #F5F3EE;
  color: #54615B;
  font-size: 13px;
}
.empty-detail { min-height: 320px; display: flex; align-items: center; justify-content: center; }

.block-title { font-size: 16px; font-weight: 700; color: #1A2420; margin-bottom: 14px; }
.block-head { display: flex; align-items: center; justify-content: space-between; }
.block-head .block-title { margin-bottom: 14px; }
.explain-row { display: flex; gap: 12px; margin-bottom: 14px; }
.explain-label { flex-shrink: 0; width: 84px; font-size: 12px; color: #8C9690; padding-top: 2px; }
.explain-row p { margin: 0; font-size: 14px; line-height: 1.7; color: #1A2420; }
.rule-line { display: flex; gap: 12px; align-items: baseline; }
.rule-line code {
  font-size: 12px;
  line-height: 1.6;
  padding: 6px 10px;
  border-radius: 10px;
  background: #F5F3EE;
  color: #164A33;
  word-break: break-all;
}
.rule-meta { margin: 10px 0 0 96px; font-size: 12px; color: #8C9690; }
.explain-note { margin-top: 14px; font-size: 12px; color: #8C9690; }
.ai-block {
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px dashed #E7E4DC;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.ai-head { display: flex; align-items: center; gap: 8px; }
.ai-summary { font-size: 14px; line-height: 1.8; color: #1A2420; }
.ai-line { display: flex; gap: 12px; }
.ai-line p { margin: 0; font-size: 13px; line-height: 1.7; color: #54615B; }
.ai-actions { display: flex; gap: 12px; align-items: flex-start; }
.ai-tags { display: flex; gap: 8px; flex-wrap: wrap; }
.snooze-note { margin-top: 14px; }

@media (max-width: 1180px) {
  .workbench { grid-template-columns: 300px minmax(0, 1fr); }
}
@media (max-width: 900px) {
  .workbench { grid-template-columns: 1fr; }
  .queue { position: static; max-height: none; }
}
</style>
