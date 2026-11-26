<template>
  <div>
    <div class="page-head">
      <div>
        <div class="page-title">员工管理</div>
        <div class="page-sub">陪诊员、保洁、合作方人员；派单时会按区域、技能、排班与容量综合判断</div>
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
        <span class="page-sub">员工的区域、技能、排班与每日容量共同决定他能否被派单</span>
      </div>
      <el-table v-loading="loading" :data="pagedStaff" style="width: 100%">
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column prop="name" label="姓名" width="100" />
        <el-table-column prop="phone" label="手机号" width="130" />
        <el-table-column label="服务区域" width="200">
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
        <el-table-column label="技能" min-width="160">
          <template #default="{ row }">
            <el-tag v-for="skill in row.skills" :key="skill" style="margin-right: 6px">{{ skill }}</el-tag>
            <span v-if="!row.skills?.length" class="page-sub">未填写</span>
          </template>
        </el-table-column>
        <el-table-column label="排班" min-width="190">
          <template #default="{ row }">
            <div>{{ scheduleText(row) }}</div>
            <div class="page-sub">每日容量 {{ row.daily_capacity }} 单</div>
          </template>
        </el-table-column>
        <el-table-column label="今日负载" width="100">
          <template #default="{ row }">
            <el-tag :type="loadType(row)">{{ row.today_load }} / {{ row.daily_capacity }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="接单" width="110">
          <template #default="{ row }">
            <el-tag v-if="row.on_leave_today" type="warning">今日请假</el-tag>
            <el-tag v-else :type="row.accepting_orders ? 'success' : 'info'">
              {{ row.accepting_orders ? '接单中' : '暂停' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="在岗" width="90">
          <template #default="{ row }"><el-tag :type="row.status === 'active' ? 'success' : 'info'">{{ row.status === 'active' ? '在岗' : '停用' }}</el-tag></template>
        </el-table-column>
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button link type="primary" @click="openLeaves(row)">请假</el-button>
            <el-button link :type="row.status === 'active' ? 'danger' : 'success'" @click="toggle(row)">
              {{ row.status === 'active' ? '停用' : '启用' }}
            </el-button>
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

    <el-dialog v-model="visible" :title="editingId ? '编辑员工' : '新增员工'" width="520px">
      <el-form label-width="96px">
        <el-form-item label="姓名"><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="手机号">
          <el-input v-model="form.phone" :disabled="!!editingId" />
        </el-form-item>
        <el-form-item label="服务区域">
          <el-select v-model="form.station_id" placeholder="选择区域" style="width: 100%">
            <el-option v-for="s in stations" :key="s.id" :label="s.name" :value="s.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="技能"><el-input v-model="form.skillsText" placeholder="用逗号分隔，例如 陪诊,保洁" /></el-form-item>

        <template v-if="editingId">
          <el-form-item label="工作日">
            <el-checkbox-group v-model="form.work_days">
              <el-checkbox v-for="d in WEEKDAYS" :key="d.value" :value="d.value">{{ d.label }}</el-checkbox>
            </el-checkbox-group>
          </el-form-item>
          <el-form-item label="上班时间">
            <el-time-picker v-model="form.startTime" format="HH:mm" value-format="HH:mm" placeholder="08:00" style="width: 100%" />
          </el-form-item>
          <el-form-item label="下班时间">
            <el-time-picker v-model="form.endTime" format="HH:mm" value-format="HH:mm" placeholder="18:00" style="width: 100%" />
          </el-form-item>
          <el-form-item label="每日容量">
            <el-input-number v-model="form.daily_capacity" :min="0" :max="50" />
            <span class="page-sub" style="margin-left: 10px">0 表示暂不接单</span>
          </el-form-item>
          <el-form-item label="接单开关">
            <el-switch v-model="form.accepting_orders" active-text="接单中" inactive-text="暂停接单" />
          </el-form-item>
        </template>
      </el-form>
      <template #footer>
        <el-button @click="visible = false">取消</el-button>
        <el-button type="primary" @click="save">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="leaveVisible" :title="`请假管理 · ${leaveStaff?.name || ''}`" width="560px">
      <div class="toolbar">
        <el-date-picker
          v-model="leaveRange"
          type="daterange"
          value-format="YYYY-MM-DD"
          start-placeholder="开始日期"
          end-placeholder="结束日期"
          style="width: 260px"
        />
        <el-input v-model="leaveReason" placeholder="原因（选填）" style="width: 150px" />
        <el-button type="primary" @click="addLeave">添加</el-button>
      </div>
      <el-table v-loading="leaveLoading" :data="leaveGroups" size="small" style="width: 100%">
        <el-table-column label="日期区间" min-width="190">
          <template #default="{ row }">
            {{ row.start === row.end ? row.start : `${row.start} ~ ${row.end}` }}
          </template>
        </el-table-column>
        <el-table-column label="天数" width="70">
          <template #default="{ row }">{{ row.days }}</template>
        </el-table-column>
        <el-table-column label="原因" min-width="120">
          <template #default="{ row }">{{ row.reason || '—' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="80">
          <template #default="{ row }">
            <el-button link type="danger" @click="removeLeaveGroup(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="page-sub" style="margin-top: 10px">
        按区间请假、按天落库；请假当天不会进入派单候选，到期自动恢复。
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { request } from '../api'

const staff = ref<any[]>([])
const stations = ref<any[]>([])
const stationId = ref<number | null>(null)
const loading = ref(false)
const visible = ref(false)
const editingId = ref(0)
const page = ref(1)
const pageSize = 10
const pagedStaff = computed(() =>
  staff.value.slice((page.value - 1) * pageSize, page.value * pageSize)
)

const WEEKDAYS = [
  { value: 1, label: '一' },
  { value: 2, label: '二' },
  { value: 3, label: '三' },
  { value: 4, label: '四' },
  { value: 5, label: '五' },
  { value: 6, label: '六' },
  { value: 7, label: '日' }
]
const WEEKDAY_NAMES: Record<number, string> = {
  1: '周一', 2: '周二', 3: '周三', 4: '周四', 5: '周五', 6: '周六', 7: '周日'
}

const form = reactive({
  name: '',
  phone: '',
  skillsText: '',
  station_id: null as number | null,
  work_days: [1, 2, 3, 4, 5, 6, 7] as number[],
  startTime: '08:00',
  endTime: '18:00',
  daily_capacity: 4,
  accepting_orders: true
})

const leaveVisible = ref(false)
const leaveLoading = ref(false)
const leaveStaff = ref<any>(null)
const leaves = ref<any[]>([])
const leaveRange = ref<[string, string] | null>(null)
const leaveReason = ref('')

interface LeaveGroup {
  start: string
  end: string
  days: number
  reason: string
}

const leaveGroups = computed(() => groupLeaves(leaves.value))

function nextDay(day: string) {
  const date = new Date(day + 'T00:00:00Z')
  date.setUTCDate(date.getUTCDate() + 1)
  return date.toISOString().slice(0, 10)
}

function daysBetween(start: string, end: string) {
  const diff = Date.parse(end + 'T00:00:00Z') - Date.parse(start + 'T00:00:00Z')
  return Math.round(diff / 86400000) + 1
}

// 连续日期且原因相同才合并成一段，避免把不同事由的假期揉在一起
function groupLeaves(rows: any[]): LeaveGroup[] {
  const sorted = [...rows].sort((a, b) => a.leave_date.localeCompare(b.leave_date))
  const groups: LeaveGroup[] = []
  for (const row of sorted) {
    const last = groups[groups.length - 1]
    const sameReason = last && (last.reason || '') === (row.reason || '')
    if (last && sameReason && nextDay(last.end) === row.leave_date) {
      last.end = row.leave_date
      last.days = daysBetween(last.start, last.end)
    } else {
      groups.push({
        start: row.leave_date,
        end: row.leave_date,
        days: 1,
        reason: row.reason || ''
      })
    }
  }
  return groups
}

function pad(value: number) {
  return String(value).padStart(2, '0')
}
function minutesToTime(minutes: number) {
  return `${pad(Math.floor(minutes / 60))}:${pad(minutes % 60)}`
}
function timeToMinutes(value: string) {
  const [hour, minute] = value.split(':').map(Number)
  return hour * 60 + minute
}
function scheduleText(row: any) {
  const days = (row.work_days || []).length === 7
    ? '每天'
    : (row.work_days || []).map((day: number) => WEEKDAY_NAMES[day]).join('、')
  return `${days || '未设置'} ${minutesToTime(row.work_start_minute)}-${minutesToTime(row.work_end_minute)}`
}
function loadType(row: any) {
  if (!row.daily_capacity) return 'info'
  if (row.today_load >= row.daily_capacity) return 'danger'
  if (row.today_load > 0) return 'warning'
  return 'success'
}

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

function resetForm() {
  form.name = ''
  form.phone = ''
  form.skillsText = ''
  form.station_id = stations.value[0]?.id || null
  form.work_days = [1, 2, 3, 4, 5, 6, 7]
  form.startTime = '08:00'
  form.endTime = '18:00'
  form.daily_capacity = 4
  form.accepting_orders = true
}

function openCreate() {
  editingId.value = 0
  resetForm()
  visible.value = true
}

function openEdit(row: any) {
  editingId.value = row.id
  form.name = row.name
  form.phone = row.phone || ''
  form.skillsText = (row.skills || []).join(',')
  form.station_id = row.station_id
  form.work_days = [...(row.work_days || [1, 2, 3, 4, 5, 6, 7])]
  form.startTime = minutesToTime(row.work_start_minute)
  form.endTime = minutesToTime(row.work_end_minute)
  form.daily_capacity = row.daily_capacity
  form.accepting_orders = row.accepting_orders
  visible.value = true
}

async function save() {
  if (!form.name || (!editingId.value && !form.phone)) {
    ElMessage.warning('姓名和手机号必填')
    return
  }
  if (!form.station_id) {
    ElMessage.warning('请选择服务区域')
    return
  }
  const skills = form.skillsText.split(',').map(s => s.trim()).filter(Boolean)
  if (!editingId.value) {
    await request('/admin/staff', {
      method: 'POST',
      body: { name: form.name, phone: form.phone, skills, station_id: form.station_id }
    })
    ElMessage.success('已新增；排班与容量可再点「编辑」补充')
  } else {
    if (!form.work_days.length) {
      ElMessage.warning('至少选择一个工作日')
      return
    }
    if (!form.startTime || !form.endTime) {
      ElMessage.warning('请选择上下班时间')
      return
    }
    const startMinute = timeToMinutes(form.startTime)
    const endMinute = timeToMinutes(form.endTime)
    if (startMinute >= endMinute) {
      ElMessage.warning('上班时间必须早于下班时间')
      return
    }
    await request('/admin/staff/' + editingId.value, {
      method: 'PATCH',
      body: {
        name: form.name,
        skills,
        station_id: form.station_id,
        work_days: form.work_days,
        work_start_minute: startMinute,
        work_end_minute: endMinute,
        daily_capacity: form.daily_capacity,
        accepting_orders: form.accepting_orders
      }
    })
    ElMessage.success('已保存')
  }
  visible.value = false
  await load()
}

async function changeStation(row: any, value: number) {
  await request('/admin/staff/' + row.id, { method: 'PATCH', body: { station_id: value } })
  ElMessage.success('区域已更新')
  await load()
}

async function toggle(row: any) {
  const action = row.status === 'active' ? '停用' : '启用'
  try {
    await ElMessageBox.confirm(
      row.status === 'active' ? '停用后该员工将不再参与派单，确认？' : '启用后该员工可重新参与派单，确认？',
      action + '员工',
      { type: 'warning', confirmButtonText: '确认' + action, cancelButtonText: '取消' }
    )
  } catch {
    return
  }
  await request('/admin/staff/' + row.id, {
    method: 'PATCH',
    body: { status: row.status === 'active' ? 'disabled' : 'active' }
  })
  await load()
}

async function openLeaves(row: any) {
  leaveStaff.value = row
  leaveRange.value = null
  leaveReason.value = ''
  leaveVisible.value = true
  await loadLeaves()
}

async function loadLeaves() {
  if (!leaveStaff.value) return
  leaveLoading.value = true
  try {
    leaves.value = await request(`/admin/staff/${leaveStaff.value.id}/leaves`)
  } finally {
    leaveLoading.value = false
  }
}

async function addLeave() {
  if (!leaveRange.value || leaveRange.value.length !== 2) {
    ElMessage.warning('请选择请假日期区间')
    return
  }
  const [start, end] = leaveRange.value
  await request(`/admin/staff/${leaveStaff.value.id}/leaves`, {
    method: 'POST',
    body: { start_date: start, end_date: end, reason: leaveReason.value }
  })
  leaveRange.value = null
  leaveReason.value = ''
  await loadLeaves()
  await load()
}

async function removeLeaveGroup(row: LeaveGroup) {
  const label = row.start === row.end ? row.start : `${row.start} ~ ${row.end}`
  try {
    await ElMessageBox.confirm(
      `确认删除 ${label} 的 ${row.days} 天请假？`,
      '删除请假',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' }
    )
  } catch {
    return
  }
  const query = `from_date=${encodeURIComponent(row.start)}&to_date=${encodeURIComponent(row.end)}`
  await request(`/admin/staff/${leaveStaff.value.id}/leaves?${query}`, { method: 'DELETE' })
  await loadLeaves()
  await load()
}

onMounted(async () => {
  await Promise.all([load(), loadStations()])
})
</script>
