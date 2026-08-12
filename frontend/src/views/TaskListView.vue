<template>
  <div class="task-list-view">
    <div class="toolbar">
      <h2 class="page-title">任务列表</h2>
      <router-link to="/tasks/create">
        <el-button type="primary">＋ 新建任务</el-button>
      </router-link>
    </div>

    <el-card shadow="never">
      <el-table
        v-loading="loading"
        :data="tasks"
        row-key="id"
        class="task-table"
        @row-click="goDetail"
      >
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
        <el-table-column label="操作" width="90" align="center" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click.stop="goDetail(row)">详情</el-button>
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
import { fetchTasks } from '../api'
import { TASK_STATUS_MAP, formatTime, calcSuccessRate } from '../utils'

const router = useRouter()

const tasks = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const loading = ref(false)

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

function goDetail(row) {
  router.push(`/tasks/${row.id}`)
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
