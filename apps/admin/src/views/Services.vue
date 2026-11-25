<template>
  <div>
    <div class="page-head">
      <div>
        <div class="page-title">服务管理</div>
        <div class="page-sub">服务、价格、时长、上下架（下架后小程序首页不再展示）</div>
      </div>
      <div class="toolbar" style="margin: 0">
        <el-button @click="load">刷新</el-button>
        <el-button type="primary" @click="openCreate">新增服务</el-button>
      </div>
    </div>
    <div class="page-card">
      <el-alert
        v-if="activeCount === 0"
        title="当前没有上架服务，小程序首页将不展示服务入口"
        type="warning"
        :closable="false"
        show-icon
        style="margin-bottom: 16px"
      />
      <el-table v-loading="loading" :data="pagedServices" style="width: 100%">
        <el-table-column prop="code" label="编码" width="120" />
        <el-table-column prop="name" label="名称" width="130" />
        <el-table-column prop="category" label="分类" width="110" />
        <el-table-column label="价格" width="100">
          <template #default="{ row }">¥{{ money(row.price_cents) }}</template>
        </el-table-column>
        <el-table-column prop="duration_minutes" label="时长(分)" width="100" />
        <el-table-column prop="description" label="说明" min-width="260" show-overflow-tooltip />
        <el-table-column label="小程序展示" width="100">
          <template #default="{ row }"><el-tag :type="row.active ? 'success' : 'info'">{{ row.active ? '展示' : '隐藏' }}</el-tag></template>
        </el-table-column>
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button link :type="row.active ? 'danger' : 'success'" @click="toggleActive(row)">
              {{ row.active ? '下架' : '上架' }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="pager">
        <el-pagination
          background
          layout="total, prev, pager, next"
          :total="services.length"
          :page-size="pageSize"
          :current-page="page"
          @current-change="page = $event"
        />
      </div>
    </div>

    <el-dialog v-model="visible" :title="form.id ? '编辑服务' : '新增服务'" width="480px">
      <el-form label-width="80px">
        <el-form-item label="编码"><el-input v-model="form.code" :disabled="!!form.id" /></el-form-item>
        <el-form-item label="名称"><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="分类">
          <el-select v-model="form.category" style="width: 100%">
            <el-option label="陪诊" value="companion" />
            <el-option label="保洁" value="cleaning" />
            <el-option label="适老化" value="renovation" />
            <el-option label="代办" value="errand" />
            <el-option label="助餐" value="meal" />
          </el-select>
        </el-form-item>
        <el-form-item label="价格(元)"><el-input-number v-model="form.priceYuan" :min="0" :precision="2" style="width: 100%" /></el-form-item>
        <el-form-item label="时长(分)"><el-input-number v-model="form.duration_minutes" :min="0" style="width: 100%" /></el-form-item>
        <el-form-item label="说明"><el-input v-model="form.description" type="textarea" :rows="3" /></el-form-item>
        <el-form-item label="上架"><el-switch v-model="form.active" /></el-form-item>
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
import { ElMessage, ElMessageBox } from 'element-plus'
import { request } from '../api'

const services = ref<any[]>([])
const loading = ref(false)
const page = ref(1)
const pageSize = 10
const pagedServices = computed(() =>
  services.value.slice((page.value - 1) * pageSize, page.value * pageSize)
)
const activeCount = computed(() => services.value.filter(item => item.active).length)
const visible = ref(false)
const form = reactive<any>({ id: 0, code: '', name: '', category: 'companion', description: '', priceYuan: 0, duration_minutes: 60, active: true, sort: 0 })

function money(cents: number) { return ((cents || 0) / 100).toFixed(2).replace('.00', '') }
async function load() {
  loading.value = true
  try {
    services.value = await request('/admin/services')
    page.value = 1
  } finally { loading.value = false }
}
function openCreate() {
  Object.assign(form, { id: 0, code: '', name: '', category: 'companion', description: '', priceYuan: 0, duration_minutes: 60, active: true, sort: 0 })
  visible.value = true
}
function openEdit(row: any) {
  Object.assign(form, { ...row, priceYuan: row.price_cents / 100 })
  visible.value = true
}
async function toggleActive(row: any) {
  const action = row.active ? '下架' : '上架'
  try {
    await ElMessageBox.confirm(
      row.active
        ? '下架后小程序首页将不再展示该服务，其他已上架服务不受影响。确认下架？'
        : '上架后小程序首页会重新展示该服务。确认上架？',
      action + '服务',
      { type: 'warning', confirmButtonText: '确认' + action, cancelButtonText: '取消' }
    )
  } catch {
    return
  }
  await request('/admin/services/' + row.id, {
    method: 'PATCH',
    body: {
      code: row.code,
      name: row.name,
      category: row.category,
      description: row.description,
      price_cents: row.price_cents,
      duration_minutes: row.duration_minutes,
      unit: row.unit,
      active: !row.active,
      sort: row.sort
    }
  })
  ElMessage.success(action + '成功')
  await load()
}

async function save() {
  if (!form.code || !form.name) {
    ElMessage.warning('编码和名称必填')
    return
  }
  const payload = {
    code: form.code,
    name: form.name,
    category: form.category,
    description: form.description,
    price_cents: Math.round(Number(form.priceYuan) * 100),
    duration_minutes: Number(form.duration_minutes),
    unit: form.unit || '次',
    active: form.active,
    sort: Number(form.sort || 0)
  }
  if (form.id) {
    await request('/admin/services/' + form.id, { method: 'PATCH', body: payload })
  } else {
    await request('/admin/services', { method: 'POST', body: payload })
  }
  ElMessage.success('已保存')
  visible.value = false
  await load()
}
onMounted(load)
</script>
