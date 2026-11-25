<template>
  <div>
    <div class="page-head">
      <div>
        <div class="page-title">工作台</div>
        <div class="page-sub">今天的单量、待处理事项和收入</div>
      </div>
      <el-button @click="load">刷新</el-button>
    </div>

    <div class="stat-grid">
      <div class="stat-card">
        <div class="stat-label">今日订单</div>
        <div class="stat-value green">{{ stats.today_orders }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">待确认</div>
        <div class="stat-value orange">{{ stats.pending_confirm }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">服务中</div>
        <div class="stat-value orange">{{ stats.in_service }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">累计已收款</div>
        <div class="stat-value green">¥{{ money(stats.revenue_cents) }}</div>
      </div>
    </div>

    <div class="page-card" style="margin-top: 16px">
      <div class="page-head">
        <div class="page-title" style="font-size: 16px">最近订单</div>
        <el-button link type="primary" @click="$router.push('/orders')">全部订单</el-button>
      </div>
      <el-table :data="orders" style="width: 100%">
        <el-table-column prop="order_no" label="订单号" min-width="180" />
        <el-table-column prop="service_name" label="服务" width="120" />
        <el-table-column prop="elder_name" label="老人" width="100" />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="tagType(row.status)">{{ statusText(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="金额" width="100">
          <template #default="{ row }">¥{{ money(row.amount_cents) }}</template>
        </el-table-column>
        <el-table-column prop="scheduled_at" label="预约时间" min-width="150">
          <template #default="{ row }">{{ formatTime(row.scheduled_at) }}</template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { request } from '../api'

const stats = ref({ today_orders: 0, pending_confirm: 0, assigned: 0, in_service: 0, completed_today: 0, revenue_cents: 0, total_customers: 0, total_elders: 0 })
const orders = ref<any[]>([])

const STATUS: Record<string, string> = {
  pending_confirm: '待确认', confirmed: '已确认', assigned: '已派单', in_service: '服务中', completed: '已完成', cancelled: '已取消'
}

function statusText(status: string) { return STATUS[status] || status }
function tagType(status: string) {
  if (status === 'completed' || status === 'confirmed' || status === 'assigned') return 'success'
  if (status === 'pending_confirm' || status === 'in_service') return 'warning'
  return 'info'
}
function money(cents: number) { return ((cents || 0) / 100).toFixed(2).replace('.00', '') }
function formatTime(value: string) { return value ? value.replace('T', ' ').slice(0, 16) : '' }

async function load() {
  stats.value = await request('/admin/stats')
  const data = await request('/admin/orders?page=1&page_size=10')
  orders.value = data.items || []
}

onMounted(load)
</script>
