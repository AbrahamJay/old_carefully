<template>
  <div>
    <div class="page-head">
      <div>
        <div class="page-title">区域管理</div>
        <div class="page-sub">街道 / 社区服务区域；新增后给员工和长辈分配</div>
      </div>
      <div class="toolbar" style="margin: 0">
        <el-button @click="load">刷新</el-button>
        <el-button type="primary" @click="openCreate">新增区域</el-button>
      </div>
    </div>

    <div class="page-card">
      <el-table v-loading="loading" :data="pagedStations" style="width: 100%">
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="name" label="区域名称" min-width="260" />
        <el-table-column prop="street" label="街道" width="150" />
        <el-table-column prop="address" label="地址" min-width="180" />
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.active ? 'success' : 'info'">{{ row.active ? '启用' : '停用' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="160">
          <template #default="{ row }">
            <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button link :type="row.active ? 'danger' : 'success'" @click="toggle(row)">
              {{ row.active ? '停用' : '启用' }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="pager">
        <el-pagination
          background
          layout="total, prev, pager, next"
          :total="stations.length"
          :page-size="pageSize"
          :current-page="page"
          @current-change="page = $event"
        />
      </div>
    </div>

    <el-alert
      title="新增区域后，请到「员工管理」给员工选区域，到「老人档案」把长辈归到区域；派单只会匹配同区域员工。"
      type="info"
      :closable="false"
      show-icon
      style="margin-top: 16px"
    />

    <el-dialog v-model="visible" :title="form.id ? '编辑区域' : '新增区域'" width="480px">
      <el-form label-width="90px">
        <el-form-item label="区域名称">
          <el-input v-model="form.name" placeholder="例如：示范街道 · 示范社区" />
        </el-form-item>
        <el-form-item label="街道">
          <el-input v-model="form.street" placeholder="例如：示范街道" />
        </el-form-item>
        <el-form-item label="地址">
          <el-input v-model="form.address" placeholder="服务站地址" />
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="form.active" />
        </el-form-item>
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

const stations = ref<any[]>([])
const loading = ref(false)
const visible = ref(false)
const page = ref(1)
const pageSize = 10
const pagedStations = computed(() =>
  stations.value.slice((page.value - 1) * pageSize, page.value * pageSize)
)
const form = reactive({ id: 0, name: '', street: '', address: '', active: true })

async function load() {
  loading.value = true
  try {
    stations.value = await request('/admin/stations')
    page.value = 1
  } finally {
    loading.value = false
  }
}

function openCreate() {
  Object.assign(form, { id: 0, name: '', street: '', address: '', active: true })
  visible.value = true
}

function openEdit(row: any) {
  Object.assign(form, {
    id: row.id,
    name: row.name,
    street: row.street,
    address: row.address,
    active: row.active
  })
  visible.value = true
}

async function save() {
  if (!form.name.trim()) {
    ElMessage.warning('区域名称必填')
    return
  }
  const body = {
    name: form.name.trim(),
    street: form.street.trim(),
    address: form.address.trim(),
    active: form.active
  }
  if (form.id) {
    await request('/admin/stations/' + form.id, { method: 'PATCH', body })
  } else {
    await request('/admin/stations', { method: 'POST', body })
  }
  ElMessage.success('已保存')
  visible.value = false
  await load()
}

async function toggle(row: any) {
  await request('/admin/stations/' + row.id, {
    method: 'PATCH',
    body: { active: !row.active }
  })
  ElMessage.success(row.active ? '已停用' : '已启用')
  await load()
}

onMounted(load)
</script>
