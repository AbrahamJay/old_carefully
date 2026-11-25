<template>
  <div>
    <div class="page-head">
      <div>
        <div class="page-title">老人档案</div>
        <div class="page-sub">共 {{ elders.length }} 位老人</div>
      </div>
      <el-button @click="load">刷新</el-button>
    </div>
    <div class="page-card">
      <div class="toolbar">
        <el-select v-model="stationId" placeholder="全部区域" clearable style="width: 220px" @change="onFilter">
          <el-option v-for="s in stations" :key="s.id" :label="s.name" :value="s.id" />
        </el-select>
        <span class="page-sub">按服务区域筛选长辈档案</span>
      </div>
      <el-table v-loading="loading" :data="pagedElders" style="width: 100%">
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="name" label="姓名" width="100" />
        <el-table-column label="区域" width="220">
          <template #default="{ row }">{{ row.station_name || '未分配' }}</template>
        </el-table-column>
        <el-table-column prop="phone" label="电话" width="130" />
        <el-table-column prop="community" label="社区" width="120" />
        <el-table-column prop="address" label="地址" min-width="180" />
        <el-table-column label="紧急联系人" min-width="180">
          <template #default="{ row }">{{ row.emergency_name }} {{ row.emergency_phone }}</template>
        </el-table-column>
        <el-table-column prop="health_notes" label="健康备注" min-width="200" show-overflow-tooltip />
      </el-table>
      <div class="pager">
        <el-pagination
          background
          layout="total, prev, pager, next"
          :total="elders.length"
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

const elders = ref<any[]>([])
const stations = ref<any[]>([])
const stationId = ref<number | null>(null)
const loading = ref(false)
const page = ref(1)
const pageSize = 10
const pagedElders = computed(() =>
  elders.value.slice((page.value - 1) * pageSize, page.value * pageSize)
)

async function load() {
  loading.value = true
  try {
    const query = stationId.value ? '?station_id=' + stationId.value : ''
    elders.value = await request('/admin/elders' + query)
    page.value = 1
  } finally {
    loading.value = false
  }
}

function onFilter() {
  page.value = 1
  load()
}

async function loadStations() {
  stations.value = await request('/admin/stations')
}

onMounted(async () => {
  await Promise.all([load(), loadStations()])
})
</script>
