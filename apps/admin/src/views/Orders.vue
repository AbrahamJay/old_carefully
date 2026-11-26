<template>
  <div>
    <div class="page-head">
      <div>
        <div class="page-title">订单管理</div>
        <div class="page-sub">确认 → 派单 → 员工履约 → 标记收款 → 评价</div>
      </div>
      <el-button @click="load">刷新</el-button>
    </div>

    <div class="page-card">
      <div class="toolbar">
        <el-select v-model="stationId" placeholder="全部区域" clearable style="width: 220px" @change="search">
          <el-option v-for="s in stations" :key="s.id" :label="s.name" :value="s.id" />
        </el-select>
        <el-select v-model="status" placeholder="全部状态" clearable style="width: 150px" @change="search">
          <el-option label="待确认" value="pending_confirm" />
          <el-option label="已确认" value="confirmed" />
          <el-option label="已派单" value="assigned" />
          <el-option label="服务中" value="in_service" />
          <el-option label="已完成" value="completed" />
          <el-option label="已取消" value="cancelled" />
        </el-select>
        <el-input
          v-model="keyword"
          placeholder="订单号 / 长辈 / 电话"
          clearable
          style="width: 220px"
          @keyup.enter="search"
          @clear="search"
        />
        <el-button type="primary" @click="search">查询</el-button>
        <span class="page-sub">共 {{ total }} 单</span>
      </div>

      <el-table v-loading="loading" :data="orders" style="width: 100%">
        <el-table-column prop="order_no" label="订单号" min-width="200" />
        <el-table-column prop="service_name" label="服务" width="110" />
        <el-table-column prop="elder_name" label="老人" width="90" />
        <el-table-column label="区域" width="180">
          <template #default="{ row }">{{ row.station_name || '未分配' }}</template>
        </el-table-column>
        <el-table-column label="服务人员" width="110">
          <template #default="{ row }">{{ row.staff_name || '待派单' }}</template>
        </el-table-column>
        <el-table-column label="状态" width="96">
          <template #default="{ row }">
            <el-tag :type="tagType(row.status)">{{ statusText(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="收款" width="100">
          <template #default="{ row }">
            <span :class="row.payment_status === 'unpaid' ? 'warn' : 'ok'">{{ payText(row.payment_status) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="金额" width="90">
          <template #default="{ row }">¥{{ money(row.amount_cents) }}</template>
        </el-table-column>
        <el-table-column label="预约时间" min-width="140">
          <template #default="{ row }">{{ formatTime(row.scheduled_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="260" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openDetail(row)">详情</el-button>
            <el-button v-if="canConfirmOrAssign(row, 'pending_confirm')" link type="success" @click="confirmOrder(row)">确认</el-button>
            <el-button v-if="canConfirmOrAssign(row, 'confirmed')" link type="warning" @click="openAssign(row)">派单</el-button>
            <el-button v-if="canConfirmOrAssign(row, 'assigned')" link type="warning" @click="openAssign(row)">改派</el-button>
            <el-button v-if="canMarkPaid(row)" link type="success" @click="markPaid(row)">{{ payActionText(row) }}</el-button>
            <el-button v-if="canRefund(row)" link type="danger" @click="refundOrder(row)">退款</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pager">
        <el-pagination
          background
          layout="total, prev, pager, next"
          :total="total"
          :page-size="pageSize"
          :current-page="page"
          @current-change="onPageChange"
        />
      </div>
    </div>

    <el-drawer v-model="detailVisible" title="订单详情" size="560px">
      <div v-if="detail" v-loading="detailLoading">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="订单号" :span="2">{{ detail.order_no }}</el-descriptions-item>
          <el-descriptions-item label="服务">{{ detail.service?.name }}</el-descriptions-item>
          <el-descriptions-item label="金额">¥{{ money(detail.amount_cents) }}</el-descriptions-item>
          <el-descriptions-item label="区域">{{ detail.station_name || '未分配' }}</el-descriptions-item>
          <el-descriptions-item label="定金">¥{{ money(detail.deposit_cents) }}</el-descriptions-item>
          <el-descriptions-item label="已付">¥{{ money(detail.paid_cents) }}</el-descriptions-item>
          <el-descriptions-item label="待付">¥{{ money(detail.remaining_cents) }}</el-descriptions-item>
          <el-descriptions-item label="状态">
            <el-tag :type="tagType(detail.status)">{{ statusText(detail.status) }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="收款">{{ payText(detail.payment_status) }}</el-descriptions-item>
          <el-descriptions-item label="老人">{{ detail.elder?.name }}</el-descriptions-item>
          <el-descriptions-item label="联系电话">{{ detail.elder?.phone }}</el-descriptions-item>
          <el-descriptions-item label="地址" :span="2">{{ detail.address }}</el-descriptions-item>
          <el-descriptions-item label="预约时间" :span="2">{{ formatTime(detail.scheduled_at) }}</el-descriptions-item>
          <el-descriptions-item label="服务人员">{{ detail.staff?.name || '未派单' }}</el-descriptions-item>
          <el-descriptions-item label="备注">{{ detail.notes || '无' }}</el-descriptions-item>
        </el-descriptions>

        <div class="detail-actions">
          <el-button v-if="canConfirmOrAssign(detail, 'pending_confirm')" type="success" @click="confirmOrder(detail)">确认订单</el-button>
          <el-button v-if="canConfirmOrAssign(detail, 'confirmed')" type="warning" @click="openAssign(detail)">派单</el-button>
          <el-button v-if="canConfirmOrAssign(detail, 'assigned')" type="warning" @click="openAssign(detail)">改派</el-button>
          <el-button v-if="canMarkPaid(detail)" type="success" @click="markPaid(detail)">{{ payActionText(detail) }}</el-button>
          <el-button v-if="canRefund(detail)" type="danger" @click="refundOrder(detail)">退款</el-button>
        </div>

        <h4>服务记录</h4>
        <el-empty v-if="!detail.records?.length" description="员工还未提交记录" />
        <div v-for="record in detail.records" :key="record.id" class="record">
          <div class="record-time">{{ formatTime(record.checkin_at) }} · 家属已确认：{{ record.elder_confirmed ? '是' : '否' }}</div>
          <div class="record-content">{{ record.content }}</div>
          <div class="photos" v-if="record.photos?.length">
            <el-image
              v-for="photo in record.photos"
              :key="photo"
              :src="HOST + photo"
              :preview-src-list="record.photos.map((p) => HOST + p)"
              fit="cover"
              class="photo"
            />
          </div>
        </div>

        <h4>评价</h4>
        <el-empty v-if="!detail.review" description="暂无评价" />
        <div v-else class="record">
          <el-rate :model-value="detail.review.rating" disabled />
          <div class="record-content">{{ detail.review.content }}</div>
        </div>
      </div>
    </el-drawer>

    <el-dialog
      v-model="assignVisible"
      :title="assignOrder?.status === 'assigned' ? '改派服务人员' : '派单给员工'"
      width="460px"
    >
      <div class="assign-area">
        <span>服务区域</span>
        <strong>{{ assignOrder?.station_name || '未分配' }}</strong>
      </div>
      <el-select v-model="assignStaffId" placeholder="选择同区域员工" style="width: 100%">
        <el-option
          v-for="s in assignStaff"
          :key="s.id"
          :label="s.name + '（' + (s.skills || []).join('、') + '）'"
          :value="s.id"
        />
      </el-select>
      <el-empty
        v-if="!assignStaff.length"
        description="该区域暂无可用员工，请先在员工管理里配置区域"
        :image-size="60"
      />
      <div class="assign-hint">只显示当前订单区域内的员工；跨区域派单会被后端拒绝。</div>
      <template #footer>
        <el-button @click="assignVisible = false">取消</el-button>
        <el-button type="primary" :disabled="!assignStaff.length" @click="doAssign">确认派单</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { request } from '../api'

const route = useRoute()

// 图片地址由后端返回相对路径（/api/v1/files/<key>），必须保持同源：
// 开发走 vite 代理，生产走入口 nginx 的 /api/ 反代，不能再拼 127.0.0.1。
const HOST = ''
const STATUS: Record<string, string> = {
  pending_confirm: '待确认', confirmed: '已确认', assigned: '已派单', in_service: '服务中', completed: '已完成', cancelled: '已取消'
}
const PAY: Record<string, string> = { unpaid: '未收款', deposit_paid: '已付定金', paid_offline: '已收款', paid_mock: '已收款', refunded: '已退款' }

const orders = ref<any[]>([])
const stations = ref<any[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 10
const status = ref('')
const stationId = ref<number | null>(null)
const keyword = ref('')
const loading = ref(false)
const detail = ref<any>(null)
const detailVisible = ref(false)
const detailLoading = ref(false)
const assignVisible = ref(false)
const assignOrder = ref<any>(null)
const assignStaff = ref<any[]>([])
const assignStaffId = ref<number | null>(null)

function statusText(value: string) { return STATUS[value] || value }
function payText(value: string) { return PAY[value] || value }
function tagType(value: string) {
  if (['completed', 'confirmed', 'assigned'].includes(value)) return 'success'
  if (['pending_confirm', 'in_service'].includes(value)) return 'warning'
  return 'info'
}
function money(cents: number) { return ((cents || 0) / 100).toFixed(2).replace('.00', '') }
function canMarkPaid(row: any) {
  return ['pending_confirm', 'confirmed', 'assigned', 'in_service', 'completed'].includes(row.status) &&
    ['unpaid', 'deposit_paid'].includes(row.payment_status)
}
function payActionText(row: any) {
  if (row.payment_status === 'unpaid') return '标记定金'
  if (row.payment_status === 'deposit_paid') return '标记尾款'
  return ''
}
function canRefund(row: any) {
  return Number(row.paid_cents || 0) > 0 && row.payment_status !== 'refunded'
}
// 已退款订单只留历史：不再允许确认/派单/改派，等人工或系统把它收尾到已取消
function canConfirmOrAssign(row: any, status: string) {
  return row.status === status && row.payment_status !== 'refunded'
}
function formatTime(value: string) { return value ? value.replace('T', ' ').slice(0, 16) : '' }

async function load() {
  loading.value = true
  try {
    const params = new URLSearchParams({ page: String(page.value), page_size: String(pageSize) })
    if (status.value) params.set('status', status.value)
    if (stationId.value) params.set('station_id', String(stationId.value))
    if (keyword.value.trim()) params.set('keyword', keyword.value.trim())
    const data = await request('/admin/orders?' + params.toString())
    orders.value = data.items || []
    total.value = data.total || 0
  } finally {
    loading.value = false
  }
}

function search() {
  page.value = 1
  load()
}

function onPageChange(value: number) {
  page.value = value
  load()
}

async function loadStations() {
  stations.value = await request('/admin/stations')
}

async function openDetail(row: any) {
  detailVisible.value = true
  detailLoading.value = true
  try {
    detail.value = await request('/orders/' + row.id)
  } finally {
    detailLoading.value = false
  }
}

async function confirmOrder(row: any) {
  try {
    await request('/orders/' + row.id + '/confirm', { method: 'POST' })
    ElMessage.success('已确认')
    await load()
    if (detail.value?.id === row.id) await openDetail(row)
  } catch (e: any) {
    ElMessage.error(e.message)
  }
}

async function openAssign(row: any) {
  assignOrder.value = row
  assignStaffId.value = null
  assignVisible.value = true
  const query = row.station_id ? '?station_id=' + row.station_id : ''
  assignStaff.value = await request('/admin/staff' + query)
  if (assignStaff.value.length === 1) {
    assignStaffId.value = assignStaff.value[0].id
  }
}

async function doAssign() {
  if (!assignStaffId.value) {
    ElMessage.warning('请选择员工')
    return
  }
  try {
    await request('/orders/' + assignOrder.value.id + '/assign', {
      method: 'POST',
      body: { staff_id: assignStaffId.value }
    })
    ElMessage.success(assignOrder.value.status === 'assigned' ? '已改派' : '已派单')
    assignVisible.value = false
    await load()
    if (detail.value?.id === assignOrder.value.id) await openDetail(assignOrder.value)
  } catch (e: any) {
    ElMessage.error(e.message)
  }
}

async function markPaid(row: any) {
  const label = row.payment_status === 'unpaid' ? '定金' : '尾款'
  try {
    await ElMessageBox.confirm('确认已线下收到' + label + '？', '标记' + label, { type: 'warning' })
  } catch {
    return
  }
  try {
    await request('/orders/' + row.id + '/pay-offline', { method: 'POST', body: { method: 'offline' } })
    ElMessage.success('已标记' + label)
    await load()
    if (detail.value?.id === row.id) await openDetail(row)
  } catch (e: any) {
    ElMessage.error(e.message)
  }
}

async function refundOrder(row: any) {
  const amount = money(row.paid_cents || 0)
  try {
    await ElMessageBox.confirm('确认退款 ¥' + amount + '？退款后订单支付状态会变为已退款。', '退款', { type: 'warning' })
  } catch {
    return
  }
  try {
    await request('/orders/' + row.id + '/refund', { method: 'POST' })
    ElMessage.success('已退款')
    await load()
    if (detail.value?.id === row.id) await openDetail(row)
  } catch (e: any) {
    ElMessage.error(e.message)
  }
}

onMounted(async () => {
  // 异常巡检「去处理这一单」带订单号跳过来：定位到该单并展开详情
  const fromQuery = route.query.keyword
  if (typeof fromQuery === 'string' && fromQuery) keyword.value = fromQuery
  await Promise.all([load(), loadStations()])
  if (keyword.value && orders.value.length === 1) await openDetail(orders.value[0])
})
</script>

<style scoped>
.warn { color: #c25e0a; }
.ok { color: #1f5d3f; }
.pager { display: flex; justify-content: flex-end; margin-top: 16px; }
.assign-area {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  margin-bottom: 14px;
  border-radius: 12px;
  background: #F5F3EE;
  color: #54615B;
  font-size: 13px;
}
.assign-area strong { color: #1A2420; }
.assign-hint { margin-top: 12px; color: #8C9690; font-size: 12px; line-height: 1.6; }
.detail-actions { margin: 16px 0; display: flex; gap: 8px; }
h4 { margin: 18px 0 10px; }
.record { border-top: 1px solid #eef0f3; padding: 12px 0; }
.record-time { color: #8a8f99; font-size: 12px; }
.record-content { margin-top: 6px; color: #374151; }
.photos { display: flex; gap: 8px; margin-top: 8px; }
.photo { width: 90px; height: 90px; border-radius: 6px; }
</style>
