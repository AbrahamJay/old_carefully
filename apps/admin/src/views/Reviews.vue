<template>
  <div>
    <div class="page-head">
      <div>
        <div class="page-title">服务评价</div>
        <div class="page-sub">共 {{ reviews.length }} 条</div>
      </div>
      <el-button @click="load">刷新</el-button>
    </div>
    <div class="page-card">
      <el-table v-loading="loading" :data="pagedReviews" style="width: 100%">
        <el-table-column prop="order_no" label="订单号" min-width="180" />
        <el-table-column prop="elder_name" label="老人" width="100" />
        <el-table-column prop="service_name" label="服务" width="120" />
        <el-table-column label="评分" width="150">
          <template #default="{ row }"><el-rate :model-value="row.rating" disabled /></template>
        </el-table-column>
        <el-table-column prop="content" label="内容" min-width="260" show-overflow-tooltip />
        <el-table-column label="时间" min-width="140">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
      </el-table>
      <div class="pager">
        <el-pagination
          background
          layout="total, prev, pager, next"
          :total="reviews.length"
          :page-size="pageSize"
          :current-page="page"
          @current-change="page = $event"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { request } from '../api'

const reviews = ref<any[]>([])
const loading = ref(false)
const page = ref(1)
const pageSize = 10
const pagedReviews = computed(() =>
  reviews.value.slice((page.value - 1) * pageSize, page.value * pageSize)
)
function formatTime(value: string) { return value ? value.replace('T', ' ').slice(0, 16) : '' }
async function load() {
  loading.value = true
  try {
    reviews.value = await request('/admin/reviews')
    page.value = 1
  } finally { loading.value = false }
}
onMounted(load)
</script>
