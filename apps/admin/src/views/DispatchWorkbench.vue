<template>
  <div>
    <div class="page-head">
      <div>
        <div class="page-title">派单工作台</div>
        <div class="page-sub">规则给候选，你来做确认；确认 + 派单在一个事务里完成</div>
      </div>
      <el-button @click="refreshAll">刷新</el-button>
    </div>

    <div class="stat-grid">
      <div class="stat-card">
        <div class="stat-label">待确认</div>
        <div class="stat-value orange">{{ summary.pending_confirm }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">待派单</div>
        <div class="stat-value orange">{{ summary.confirmed }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">今日已派</div>
        <div class="stat-value green">{{ summary.dispatched_today }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">今日已处理</div>
        <div class="stat-value green">{{ summary.handled_today }}</div>
      </div>
    </div>

    <div class="workbench">
      <aside class="queue page-card">
        <div class="queue-head">
          <span>待处理队列</span>
          <el-tag :type="visibleQueue.length ? 'warning' : 'info'" round>{{ visibleQueue.length }}</el-tag>
        </div>
        <el-empty v-if="!visibleQueue.length" description="暂无待确认 / 待派单订单" :image-size="72" />
        <button
          v-for="item in visibleQueue"
          :key="item.id"
          class="queue-item"
          :class="{ active: String(item.id) === orderId }"
          @click="selectOrder(item.id)"
        >
          <div class="queue-row">
            <el-tag :type="item.status === 'pending_confirm' ? 'warning' : 'info'" size="small">
              {{ statusText(item.status) }}
            </el-tag>
            <span class="order-no">{{ item.order_no }}</span>
          </div>
          <div class="queue-main">{{ item.elder_name }} · {{ item.service_name }}</div>
          <div class="queue-sub">
            预约 {{ formatTime(item.scheduled_at) }} · 已等待 {{ waitedText(item.created_at) }}
          </div>
        </button>
      </aside>

      <section v-if="current" class="detail">
        <div class="page-card">
          <div class="detail-head">
            <div>
              <div class="detail-title">{{ current.order_no }}</div>
              <div class="page-sub">{{ current.elder?.name }} · {{ current.service?.name }}</div>
            </div>
            <el-tag :type="current.status === 'pending_confirm' ? 'warning' : 'info'">
              {{ statusText(current.status) }}
            </el-tag>
          </div>

          <el-descriptions :column="2" border>
            <el-descriptions-item label="服务区域">{{ current.station_name || '未分配' }}</el-descriptions-item>
            <el-descriptions-item label="社区">{{ current.elder?.community || '未维护' }}</el-descriptions-item>
            <el-descriptions-item label="预约时间">{{ formatTime(current.scheduled_at) }}</el-descriptions-item>
            <el-descriptions-item label="服务时长">{{ current.service?.duration_minutes || 30 }} 分钟</el-descriptions-item>
            <el-descriptions-item label="老人电话">{{ current.elder?.phone || '—' }}</el-descriptions-item>
            <el-descriptions-item label="联系人">{{ current.contact_name || '—' }} {{ current.contact_phone }}</el-descriptions-item>
            <el-descriptions-item label="上门地址" :span="2">{{ current.address || '—' }}</el-descriptions-item>
            <el-descriptions-item label="家属备注" :span="2">{{ current.notes || '无' }}</el-descriptions-item>
          </el-descriptions>

          <div class="actions">
            <el-button v-if="current.status === 'pending_confirm' && !isRefunded" @click="confirmOnly">仅确认</el-button>
            <el-button @click="skipCurrent">稍后处理</el-button>
            <el-button
              type="primary"
              :disabled="!canDispatch"
              @click="openConfirm"
            >
              确认并派单
            </el-button>
          </div>
        </div>

        <div class="page-card suggestion" v-loading="candidateLoading">
          <div class="suggestion-head">
            <div>
              <div class="suggestion-title">
                <template v-if="recommendation">推荐 {{ recommendation.name }}</template>
                <template v-else>暂无可用候选</template>
              </div>
              <div class="page-sub">{{ requiredSkill ? '本单需要技能：' + requiredSkill : '该服务未配置所需技能' }}</div>
            </div>
            <el-tag v-if="recommendation" type="success" round>{{ recommendation.score }} 分</el-tag>
          </div>

          <el-alert
            v-if="!candidateLoading && !candidates.length"
            type="warning"
            :closable="false"
            show-icon
            title="没有可用候选"
            description="下面列出了每位员工被哪条规则挡住；可仅确认后稍后处理，或协调其他站点支援。"
          />

          <div v-else class="candidate-grid">
            <div
              v-for="item in candidates"
              :key="item.staff_id"
              class="candidate"
              :class="{ selected: item.staff_id === selectedStaffId }"
              @click="selectedStaffId = item.staff_id"
            >
              <div class="candidate-head">
                <span class="candidate-name">{{ item.name }}</span>
                <el-tag v-if="item.staff_id === recommendation?.staff_id" size="small" type="success">推荐</el-tag>
                <span class="candidate-score">{{ item.score }} 分</span>
              </div>
              <div class="candidate-meta">
                {{ item.station_name || '未分配站点' }} · 负载 {{ item.load }}/{{ item.capacity }} · 评分 {{ item.rating.toFixed(1) }}
              </div>
              <div class="candidate-skills">{{ (item.skills || []).join('、') || '未维护技能' }}</div>
              <ul class="reasons">
                <li v-for="reason in item.reasons" :key="reason">{{ reason }}</li>
              </ul>
              <div v-if="item.risks?.length" class="risks">
                风险：{{ item.risks.join('；') }}
              </div>
            </div>
          </div>

          <div v-if="dataGaps.length" class="gaps">
            <div class="gaps-title">数据缺口</div>
            <div v-for="gap in dataGaps" :key="gap">· {{ gap }}</div>
          </div>

          <el-collapse v-if="excluded.length" class="excluded">
            <el-collapse-item :title="`查看被排除的 ${excluded.length} 人`">
              <div v-for="item in excluded" :key="item.staff_id" class="excluded-row">
                <strong>{{ item.name }}</strong>：{{ item.reasons.join('；') }}
              </div>
            </el-collapse-item>
          </el-collapse>
        </div>
      </section>

      <section v-else class="page-card empty-detail">
        <el-empty description="从左侧队列选择一笔订单" :image-size="96" />
      </section>
    </div>

    <el-dialog v-model="confirmVisible" title="确认并派单" width="540px">
      <div v-if="current && selectedCandidate" class="confirm-body">
        <el-descriptions :column="1" border>
          <el-descriptions-item label="订单号">{{ current.order_no }}</el-descriptions-item>
          <el-descriptions-item label="老人 / 服务">
            {{ current.elder?.name }} · {{ current.service?.name }}
          </el-descriptions-item>
          <el-descriptions-item label="服务人员">{{ selectedCandidate.name }}</el-descriptions-item>
          <el-descriptions-item label="服务区域">{{ current.station_name || '未分配' }}</el-descriptions-item>
          <el-descriptions-item label="预约时间">{{ formatTime(current.scheduled_at) }}</el-descriptions-item>
        </el-descriptions>

        <div class="confirm-risk">
          <div class="confirm-risk-title">执行前请再核对</div>
          <div v-if="confirmRisks.length">
            <div v-for="risk in confirmRisks" :key="risk">· {{ risk }}</div>
          </div>
          <div v-else>· 无已知风险，请再次核对时间与地址</div>
          <div v-if="current.status === 'pending_confirm'">· 本次操作会同时确认订单并派单</div>
        </div>
      </div>
      <template #footer>
        <el-button :disabled="executing" @click="confirmVisible = false">取消</el-button>
        <el-button type="primary" :loading="executing" @click="execute">确认执行</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { request } from '../api'

const STATUS: Record<string, string> = {
  pending_confirm: '待确认', confirmed: '待派单', assigned: '已派单', in_service: '服务中', completed: '已完成', cancelled: '已取消'
}

const route = useRoute()
const router = useRouter()

const summary = ref({ pending_confirm: 0, confirmed: 0, dispatched_today: 0, handled_today: 0 })
const queue = ref<any[]>([])
const skipped = ref<Set<number>>(new Set())
const current = ref<any>(null)
const candidates = ref<any[]>([])
const excluded = ref<any[]>([])
const dataGaps = ref<string[]>([])
const recommendation = ref<any>(null)
const requiredSkill = ref<string | null>(null)
const selectedStaffId = ref<number | null>(null)
const candidateLoading = ref(false)
const confirmVisible = ref(false)
const executing = ref(false)

const orderId = computed(() => (route.query.order ? String(route.query.order) : ''))
const visibleQueue = computed(() => queue.value.filter((item) => !skipped.value.has(item.id)))
const selectedCandidate = computed(
  () => candidates.value.find((item) => item.staff_id === selectedStaffId.value) || null
)
const canDispatch = computed(
  () => !!current.value && !isRefunded.value && ['pending_confirm', 'confirmed'].includes(current.value.status) && !!selectedStaffId.value
)
// 已退款订单不进待派单队列（历史数据可能还停在已确认）
const isRefunded = computed(() => current.value?.payment_status === 'refunded')
const confirmRisks = computed(() => {
  const risks: string[] = []
  if (selectedCandidate.value?.risks?.length) risks.push(...selectedCandidate.value.risks)
  risks.push(...dataGaps.value)
  return risks
})

function statusText(value: string) { return STATUS[value] || value }
function formatTime(value: string) { return value ? value.replace('T', ' ').slice(0, 16) : '—' }
function waitedText(value: string) {
  if (!value) return '—'
  const minutes = Math.max(0, Math.floor((Date.now() - new Date(value).getTime()) / 60000))
  if (minutes < 60) return `${minutes} 分钟`
  return `${(minutes / 60).toFixed(1)} 小时`
}

function notifyLayout() {
  window.dispatchEvent(new Event('dispatch:refresh'))
}

async function loadSummary() {
  try {
    summary.value = await request('/admin/dispatch/summary')
  } catch {
    // 概览失败不阻断队列；登录过期由 request 统一处理
  }
}

async function loadQueue() {
  const [pending, confirmed] = await Promise.all([
    request('/admin/orders?status=pending_confirm&page_size=200'),
    request('/admin/orders?status=confirmed&page_size=200')
  ])
  queue.value = [...(pending.items || []), ...(confirmed.items || [])]
    .filter((item) => item.payment_status !== 'refunded')
    .sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime())
}

async function loadDetail(id: number) {
  candidateLoading.value = true
  try {
    const [detail, report] = await Promise.all([
      request('/orders/' + id),
      request(`/admin/orders/${id}/candidates`)
    ])
    current.value = detail
    candidates.value = report.candidates || []
    excluded.value = report.excluded || []
    dataGaps.value = report.data_gaps || []
    recommendation.value = report.recommendation || null
    requiredSkill.value = report.required_skill || null
    selectedStaffId.value =
      report.recommendation?.staff_id || candidates.value[0]?.staff_id || null
  } catch (error: any) {
    current.value = null
    ElMessage.error(error.message)
  } finally {
    candidateLoading.value = false
  }
}

function selectOrder(id: number) {
  router.replace({ path: '/dispatch', query: { order: String(id) } })
}

function nextOrderId(excludeId?: number) {
  return visibleQueue.value.find((item) => item.id !== excludeId)?.id
}

async function refreshAll() {
  skipped.value = new Set()
  await Promise.all([loadSummary(), loadQueue()])
  notifyLayout()
  const selected = orderId.value ? Number(orderId.value) : null
  if (!selected || !visibleQueue.value.some((item) => item.id === selected)) {
    const next = nextOrderId()
    if (next) {
      selectOrder(next)
    } else {
      current.value = null
      candidates.value = []
      selectedStaffId.value = null
      router.replace({ path: '/dispatch' })
    }
  }
}

function openConfirm() {
  if (!canDispatch.value) {
    ElMessage.warning('请先选择一名候选员工')
    return
  }
  confirmVisible.value = true
}

async function execute() {
  if (!current.value || !selectedStaffId.value || executing.value) return
  executing.value = true
  const staffName = selectedCandidate.value?.name || ''
  const orderIdValue = current.value.id
  try {
    await request(`/admin/orders/${orderIdValue}/confirm-and-assign`, {
      method: 'POST',
      body: {
        staff_id: selectedStaffId.value,
        expected_updated_at: current.value.updated_at
      }
    })
    confirmVisible.value = false
    ElMessage.success(`已确认并派单给 ${staffName}`)
    current.value = null
    candidates.value = []
    selectedStaffId.value = null
    await refreshAll()
  } catch (error: any) {
    // 409（已被其他人处理 / 已派单）时刷新，避免继续基于旧状态操作
    ElMessage.error(error.message)
    confirmVisible.value = false
    await refreshAll()
    if (orderId.value) {
      await loadDetail(Number(orderId.value))
    }
  } finally {
    executing.value = false
  }
}

async function confirmOnly() {
  if (!current.value) return
  try {
    await ElMessageBox.confirm(
      '只确认订单、暂不派单？订单会留在「待派单」队列。',
      '仅确认',
      { type: 'warning' }
    )
  } catch {
    return
  }
  try {
    await request(`/orders/${current.value.id}/confirm`, { method: 'POST' })
    ElMessage.success('已确认，订单仍在待派单队列')
    await refreshAll()
    // 选中项不变时 refreshAll 不会重载详情，这里手动刷新状态和候选
    if (orderId.value) await loadDetail(Number(orderId.value))
  } catch (error: any) {
    ElMessage.error(error.message)
  }
}

function skipCurrent() {
  if (!current.value) return
  skipped.value = new Set([...skipped.value, current.value.id])
  const next = nextOrderId(current.value.id)
  if (next) {
    selectOrder(next)
  } else {
    current.value = null
    router.replace({ path: '/dispatch' })
  }
  ElMessage.info('已暂时跳过，刷新后会重新出现')
}

watch(
  () => route.query.order,
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
  if (!orderId.value && visibleQueue.value.length) {
    selectOrder(visibleQueue.value[0].id)
  }
})
</script>

<style scoped>
.workbench {
  display: grid;
  grid-template-columns: 320px minmax(0, 1fr);
  gap: 16px;
  align-items: start;
  margin-top: 16px;
}
.queue {
  padding: 14px;
  max-height: calc(100vh - 230px);
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
.queue-item.active {
  background: #EAF2EC;
  box-shadow: inset 0 0 0 1px #1F6345;
}
.queue-row { display: flex; align-items: center; gap: 8px; }
.order-no { font-size: 12px; color: #8C9690; }
.queue-main { margin-top: 8px; font-size: 14px; font-weight: 600; color: #1A2420; }
.queue-sub { margin-top: 4px; font-size: 12px; color: #8C9690; }

.detail { display: flex; flex-direction: column; gap: 16px; min-width: 0; }
.detail-head { display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: 16px; }
.detail-title { font-size: 18px; font-weight: 700; color: #1A2420; }
.actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 18px; }
.empty-detail { min-height: 320px; display: flex; align-items: center; justify-content: center; }

.suggestion-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
}
.suggestion-title { font-size: 16px; font-weight: 700; color: #1A2420; }
.candidate-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}
.candidate {
  border: 1px solid #E7E4DC;
  border-radius: 18px;
  padding: 16px;
  cursor: pointer;
  background: #FFFFFF;
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}
.candidate:hover { border-color: #BFD5C6; }
.candidate.selected {
  border-color: #1F6345;
  box-shadow: 0 0 0 1px #1F6345 inset;
  background: #F7FBF8;
}
.candidate-head { display: flex; align-items: center; gap: 8px; }
.candidate-name { font-size: 15px; font-weight: 700; color: #1A2420; }
.candidate-score { margin-left: auto; font-size: 13px; font-weight: 700; color: #1F6345; }
.candidate-meta { margin-top: 6px; font-size: 12px; color: #8C9690; }
.candidate-skills { margin-top: 4px; font-size: 12px; color: #54615B; }
.reasons { margin: 10px 0 0; padding: 0; list-style: none; }
.reasons li { font-size: 12px; color: #54615B; line-height: 1.8; }
.reasons li::before { content: '· '; color: #1F6345; }
.risks { margin-top: 8px; font-size: 12px; color: #C25E0A; line-height: 1.7; }
.gaps { margin-top: 14px; padding: 12px 14px; border-radius: 14px; background: #FBF4E6; color: #8A6A2F; font-size: 12px; line-height: 1.8; }
.gaps-title { font-weight: 700; margin-bottom: 2px; }
.excluded { margin-top: 12px; }
.excluded-row { font-size: 12px; color: #54615B; line-height: 1.9; }

.confirm-body { display: flex; flex-direction: column; gap: 14px; }
.confirm-risk {
  padding: 12px 14px;
  border-radius: 14px;
  background: #FBF4E6;
  color: #8A6A2F;
  font-size: 12px;
  line-height: 1.9;
}
.confirm-risk-title { font-weight: 700; margin-bottom: 2px; }

@media (max-width: 1180px) {
  .workbench { grid-template-columns: 280px minmax(0, 1fr); }
  .candidate-grid { grid-template-columns: 1fr; }
}
@media (max-width: 900px) {
  .workbench { grid-template-columns: 1fr; }
  .queue { position: static; max-height: 320px; }
}
</style>
