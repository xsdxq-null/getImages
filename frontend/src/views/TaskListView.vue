<template>
  <div class="task-list-view">
    <div class="toolbar">
      <h2 class="page-title">任务列表</h2>
      <div class="toolbar-actions">
        <el-button
          type="danger"
          plain
          :disabled="selectedRows.length === 0"
          :loading="batchDeleting"
          @click="onBatchDelete"
        >
          批量删除（{{ selectedRows.length }}）
        </el-button>
        <router-link to="/tasks/create">
          <el-button type="primary">＋ 新建任务</el-button>
        </router-link>
      </div>
    </div>

    <el-card shadow="never">
      <el-table
        v-loading="loading"
        :data="tasks"
        row-key="id"
        class="task-table"
        @row-click="goDetail"
        @selection-change="onSelectionChange"
      >
        <el-table-column type="selection" width="46" align="center" />
        <el-table-column prop="id" label="ID" width="70" align="center" />
        <el-table-column prop="name" label="任务名称" min-width="200" show-overflow-tooltip />
        <el-table-column prop="total" label="商品总数" width="100" align="center" />
        <el-table-column label="完成" width="90" align="center">
          <template #default="{ row }">{{ row.succeeded ?? 0 }}</template>
        </el-table-column>
        <el-table-column label="失败" width="90" align="center">
          <template #default="{ row }">
            <span :class="{ 'fail-count': (row.failed ?? 0) > 0 }">{{ row.failed ?? 0 }}</span>
          </template>
        </el-table-column>
        <el-table-column label="成功率" width="110" align="center">
          <template #default="{ row }">
            <span :class="{ 'rate-bad': calcSuccessRate(row.total, row.succeeded) < 100 && (row.total ?? 0) > 0 }">
              {{ calcSuccessRate(row.total, row.succeeded) }}%
            </span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="110" align="center">
          <template #default="{ row }">
            <el-tag :type="taskStatusInfo(row.status)?.type" size="small" effect="light">
              {{ taskStatusInfo(row.status)?.text ?? row.status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="创建时间" width="170" align="center">
          <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="150" align="center" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click.stop="goDetail(row)">详情</el-button>
            <el-button link type="danger" @click.stop="onDelete(row)">删除</el-button>
          </template>
        </el-table-column>
        <template #empty>
          <el-empty description="暂无任务，点击右上角「新建任务」开始" :image-size="80" />
        </template>
      </el-table>

      <div class="pagination-wrap">
        <el-pagination
          background
          layout="total, sizes, prev, pager, next, jumper"
          :total="total"
          :page-size="pageSize"
          :current-page="page"
          :page-sizes="[10, 20, 50, 100]"
          @current-change="onPageChange"
          @size-change="onSizeChange"
        />
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { fetchTasks, deleteTask, batchDeleteTasks } from '../api'
import { TASK_STATUS_MAP, formatTime, calcSuccessRate } from '../utils'

const router = useRouter()

const tasks = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const loading = ref(false)
const deletingId = ref(null)
const selectedRows = ref([])
const batchDeleting = ref(false)

let timer = null

async function load() {
  loading.value = true
  try {
    const data = await fetchTasks(page.value, pageSize.value)
    tasks.value = data.items || []
    total.value = data.total ?? 0
  } catch (e) {
    /* 错误已由 axios 拦截器提示 */
  } finally {
    loading.value = false
  }
}

function taskStatusInfo(status) {
  return TASK_STATUS_MAP[status] || { text: status, type: 'info' }
}

function onPageChange(p) {
  page.value = p
  load()
}

function onSizeChange(size) {
  pageSize.value = size
  page.value = 1
  load()
}

function goDetail(row, column) {
  // 点击复选框列（type=selection）不跳转详情，避免勾选时误跳转
  if (column && column.type === 'selection') return
  router.push(`/tasks/${row.id}`)
}

function onSelectionChange(rows) {
  selectedRows.value = rows || []
}

/** 批量删除：跳过运行中任务，删除其余并提示结果 */
async function onBatchDelete() {
  const ids = selectedRows.value.map((r) => r.id)
  if (ids.length === 0) return
  const runningCount = selectedRows.value.filter(
    (r) => r.status === 'running' || r.status === 'paused'
  ).length
  const tip = runningCount
    ? `\n其中 ${runningCount} 个任务运行中，将被跳过。`
    : ''
  try {
    await ElMessageBox.confirm(
      `确定删除选中的 ${ids.length} 个任务吗？${tip}\n将同时删除其下载的图片/视频等文件，且不可恢复。`,
      '批量删除确认',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' }
    )
  } catch {
    return // 用户取消
  }
  batchDeleting.value = true
  try {
    const data = await batchDeleteTasks(ids)
    const n = data.deleted?.length ?? 0
    const skipped = data.skipped?.length ?? 0
    if (n > 0) {
      ElMessage.success(`已删除 ${n} 个任务${skipped ? `，跳过 ${skipped} 个` : ''}`)
    } else {
      ElMessage.warning(`没有可删除的任务（${skipped} 个被跳过）`)
    }
    await load()
  } catch (e) {
    ElMessage.error('批量删除失败，请稍后重试')
  } finally {
    batchDeleting.value = false
  }
}

/** 删除任务（含关联图片等文件）；运行中任务后端返回 409 拒绝 */
async function onDelete(row) {
  if (row.status === 'running' || row.status === 'paused') {
    ElMessage.warning('任务运行中不可删除，请先取消')
    return
  }
  try {
    await ElMessageBox.confirm(
      `确定删除任务「${row.name || `#${row.id}`}」吗？\n将同时删除该任务下载的图片/视频等文件，且不可恢复。`,
      '删除确认',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' }
    )
  } catch {
    return // 用户取消
  }
  deletingId.value = row.id
  try {
    await deleteTask(row.id)
    ElMessage.success('任务已删除')
    await load()
  } catch (e) {
    if (e.response?.status === 409) {
      ElMessage.warning('任务运行中不可删除，请先取消')
    } else {
      ElMessage.error('删除失败，请稍后重试')
    }
  } finally {
    deletingId.value = null
  }
}

onMounted(() => {
  load()
  // 列表页轻量刷新，保证状态展示较新
  timer = setInterval(load, 10000)
})

onBeforeUnmount(() => {
  if (timer) clearInterval(timer)
})
</script>

<style scoped>
.task-list-view {
  max-width: 1200px;
  margin: 0 auto;
}

.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.toolbar-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.page-title {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
}

.task-table {
  cursor: pointer;
}

.fail-count {
  color: #f56c6c;
  font-weight: 600;
}

.rate-bad {
  color: #e6a23c;
}

.pagination-wrap {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}
</style>
