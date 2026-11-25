<template>
  <div>
    <div class="page-head">
      <div>
        <div class="page-title">合作供给</div>
        <div class="page-sub">家政、适老化施工、辅具等合作方</div>
      </div>
      <div class="toolbar" style="margin: 0">
        <el-button @click="load">刷新</el-button>
        <el-button type="primary" @click="visible = true">新增供给</el-button>
      </div>
    </div>
    <div class="page-card">
      <el-table v-loading="loading" :data="pagedSuppliers" style="width: 100%">
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="name" label="名称" min-width="180" />
        <el-table-column prop="category" label="分类" width="110" />
        <el-table-column prop="contact_name" label="联系人" width="110" />
        <el-table-column prop="contact_phone" label="电话" width="140" />
        <el-table-column prop="contract_status" label="合同" width="100" />
        <el-table-column prop="insurance_status" label="保险" width="100" />
        <el-table-column prop="rating" label="评分" width="80" />
      </el-table>
      <div class="pager">
        <el-pagination
          background
          layout="total, prev, pager, next"
          :total="suppliers.length"
          :page-size="pageSize"
          :current-page="page"
          @current-change="page = $event"
        />
      </div>
    </div>

    <el-dialog v-model="visible" title="新增合作供给" width="440px">
      <el-form label-width="80px">
        <el-form-item label="名称"><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="分类">
          <el-select v-model="form.category" style="width: 100%">
            <el-option label="家政保洁" value="cleaning" />
            <el-option label="适老化改造" value="renovation" />
            <el-option label="陪诊/护理" value="companion" />
          </el-select>
        </el-form-item>
        <el-form-item label="联系人"><el-input v-model="form.contact_name" /></el-form-item>
        <el-form-item label="电话"><el-input v-model="form.contact_phone" /></el-form-item>
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

const suppliers = ref<any[]>([])
const loading = ref(false)
const visible = ref(false)
const page = ref(1)
const pageSize = 10
const pagedSuppliers = computed(() =>
  suppliers.value.slice((page.value - 1) * pageSize, page.value * pageSize)
)
const form = reactive({ name: '', category: 'cleaning', contact_name: '', contact_phone: '' })

async function load() {
  loading.value = true
  try {
    suppliers.value = await request('/admin/suppliers')
    page.value = 1
  } finally { loading.value = false }
}
async function save() {
  if (!form.name) {
    ElMessage.warning('名称必填')
    return
  }
  await request('/admin/suppliers', { method: 'POST', body: { ...form } })
  ElMessage.success('已新增')
  visible.value = false
  form.name = ''
  form.contact_name = ''
  form.contact_phone = ''
  await load()
}
onMounted(load)
</script>
