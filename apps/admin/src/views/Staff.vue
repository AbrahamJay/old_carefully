<template>
  <div>
    <div class="page-head">
      <div>
        <div class="page-title">员工管理</div>
        <div class="page-sub">陪诊员、保洁、合作方人员；派单时会按区域过滤</div>
      </div>
      <div class="toolbar" style="margin: 0">
        <el-button @click="load">刷新</el-button>
        <el-button type="primary" @click="openCreate">新增员工</el-button>
      </div>
    </div>
    <div class="page-card">
      <div class="toolbar">
        <el-select v-model="stationId" placeholder="全部区域" clearable style="width: 220px" @change="onFilter">
          <el-option v-for="s in stations" :key="s.id" :label="s.name" :value="s.id" />
        </el-select>
        <span class="page-sub">员工的区域决定他能在哪些订单里被派单</span>
      </div>
      <el-table v-loading="loading" :data="pagedStaff" style="width: 100%">
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="name" label="姓名" width="120" />
        <el-table-column prop="phone" label="手机号" width="140" />
        <el-table-column label="服务区域" width="230">
          <template #default="{ row }">
            <el-select
              :model-value="row.station_id"
              size="small"
              placeholder="未分配"
              @change="(value: number) => changeStation(row, value)"
            >
              <el-option v-for="s in stations" :key="s.id" :label="s.name" :value="s.id" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="技能" min-width="200">
          <template #default="{ row }">
            <el-tag v-for="skill in row.skills" :key="skill" style="margin-right: 6px">{{ skill }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="rating" label="评分" width="80" />
        <el-table-column label="状态" width="90">
          <template #default="{ row }"><el-tag :type="row.status === 'active' ? 'success' : 'info'">{{ row.status === 'active' ? '在岗' : '停用' }}</el-tag></template>
        </el-table-column>
        <el-table-column label="操作" width="90">
          <template #default="{ row }">
            <el-button link type="primary" @click="toggle(row)">{{ row.status === 'active' ? '停用' : '启用' }}</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="pager">
        <el-pagination
          background
          layout="total, prev, pager, next"
          :total="staff.length"
          :page-size="pageSize"
          :current-page="page"
          @current-change="page = $event"
        />
      </div>
    </div>

    <el-dialog v-model="visible" title="新增员工" width="460px">
      <el-form label-width="90px">
        <el-form-item label="姓名"><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="手机号"><el-input v-model="form.phone" /></el-form-item>
        <el-form-item label="服务区域">
          <el-select v-model="form.station_id" placeholder="选择区域" style="width: 100%">
            <el-option v-for="s in stations" :key="s.id" :label="s.name" :value="s.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="技能"><el-input v-model="form.skillsText" placeholder="用逗号分隔，例如 陪诊,保洁" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="visible = false">取消</el-button>
        <el-button type="primary" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { request } from '../api'

const staff = ref<any[]>([])
const stations = ref<any[]>([])
const stationId = ref<number | null>(null)
const loading = ref(false)
const visible = ref(false)
const page = ref(1)
const pageSize = 10
const pagedStaff = computed(() =>
  staff.value.slice((page.value - 1) * pageSize, page.value * pageSize)
)
const form = reactive({ name: '', phone: '', skillsText: '', station_id: null as number | null })

async function load() {
  loading.value = true
  try {
    const query = stationId.value ? '?station_id=' + stationId.value : ''
    staff.value = await request('/admin/staff' + query)
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

function openCreate() {
  form.name = ''
  form.phone = ''
  form.skillsText = ''
  form.station_id = stations.value[0]?.id || null
  visible.value = true
}

async function save() {
  if (!form.name || !form.phone) {
    ElMessage.warning('姓名和手机号必填')
    return
  }
  if (!form.station_id) {
    ElMessage.warning('请选择服务区域')
    return
  }
  await request('/admin/staff', {
    method: 'POST',
    body: {
      name: form.name,
      phone: form.phone,
      skills: form.skillsText.split(',').map(s => s.trim()).filter(Boolean),
      station_id: form.station_id
    }
  })
  ElMessage.success('已新增')
  visible.value = false
  await load()
}

async function changeStation(row: any, value: number) {
  await request('/admin/staff/' + row.id, { method: 'PATCH', body: { station_id: value } })
  ElMessage.success('区域已更新')
  await load()
}

async function toggle(row: any) {
  await request('/admin/staff/' + row.id, {
    method: 'PATCH',
    body: { status: row.status === 'active' ? 'disabled' : 'active' }
  })
  await load()
}

onMounted(async () => {
  await Promise.all([load(), loadStations()])
})
</script>
