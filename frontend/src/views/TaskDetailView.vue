<template>
  <div v-loading="pageLoading" class="task-detail-view card-gap">
    <template v-if="task">
      <div class="page-header">
        <el-button link @click="$router.push('/')">← 返回列表</el-button>
        <div class="header-info">
          <h2 class="page-title">
            任务 #{{ task.id }}：{{ task.name }}
            <el-tag :type="taskStatusInfo.type" size="small" effect="light" class="status-tag">
              {{ taskStatusInfo.text }}
            </el-tag>
          </h2>
          <div class="header-meta">
            <span>创建于 {{ formatTime(task.created_at) }}</span>
            <span v-if="task.finished_at">｜ 结束于 {{ formatTime(task.finished_at) }}</span>
            <span v-if="task.rate_limit">｜ 限速 {{ task.rate_limit }}s/请求</span>
            <span v-if="task.concurrency">｜ 并发 {{ task.concurrency }}</span>
          </div>
        </div>
      </div>

      <!-- 进度面板 -->
      <ProgressPanel :task="task" />

      <!-- 操作区 -->
      <el-card shadow="always" class="action-card">
        <template #header><span>任务操作</span></template>
        <div class="action-bar">
          <template v-if="task.status === 'pending'">
            <el-button type="primary" :loading="acting" @click="doAction('start')">▶ 开始</el-button>
          </template>
          <template v-else-if="task.status === 'running'">
            <el-button type="warning" :loading="acting" @click="doAction('pause')">⏸ 暂停</el-button>
            <el-button type="danger" plain :loading="acting" @click="doAction('cancel')">⏹ 取消</el-button>
          </template>
          <template v-else-if="task.status === 'paused'">
            <el-button type="primary" :loading="acting" @click="doAction('resume')">▶ 续跑</el-button>
            <el-button type="danger" plain :loading="acting" @click="doAction('cancel')">⏹ 取消</el-button>
          </template>
          <template v-else>
            <!-- cancelled / done / partial：断点续传 -->
            <el-button type="primary" :loading="acting" @click="doAction('resume')">▶ 续跑</el-button>
          </template>

          <el-button
            type="success"
            :disabled="downloadDisabled"
            :loading="downloading"
            @click="downloadZip"
          >
            📦 打包下载
          </el-button>
          <span v-if="downloadDisabled" class="download-tip">
            任务运行中暂不可打包，结束后可下载
          </span>
        </div>
      </el-card>

      <!-- 商品列表 -->
      <el-card shadow="always" class="products-card">
        <template #header>
          <div class="card-header-row">
            <span>商品列表（{{ productsTotal }}）</span>
            <el-radio-group v-model="statusFilter" size="small" @change="onFilterChange">
              <el-radio-button value="">全部</el-radio-button>
              <el-radio-button value="pending">待处理</el-radio-button>
              <el-radio-button value="fetching">抓取中</el-radio-button>
              <el-radio-button value="done">完成</el-radio-button>
              <el-radio-button value="failed">失败</el-radio-button>
            </el-radio-group>
          </div>
        </template>

        <el-table
          :data="products"
          v-loading="productsLoading"
          row-key="id"
          class="products-table"
          @row-click="openProduct"
        >
          <el-table-column prop="product_id" label="商品 ID" width="140" align="center" />
          <el-table-column prop="title" label="标题" min-width="200" show-overflow-tooltip>
            <template #default="{ row }">
              <span :class="{ 'title-failed': row.status === 'failed' }">
                {{ row.title || '（无标题）' }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="100" align="center">
            <template #default="{ row }">
              <el-tag :type="productStatusInfo(row.status).type" size="small">
                {{ productStatusInfo(row.status).text }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="主图" width="90" align="center">
            <template #default="{ row }">{{ resourceCountText(row, 'main_image') }}</template>
          </el-table-column>
          <el-table-column label="详情图" width="90" align="center">
            <template #default="{ row }">{{ resourceCountText(row, 'detail_image') }}</template>
          </el-table-column>
          <el-table-column label="主图视频" width="90" align="center">
            <template #default="{ row }">{{ resourceCountText(row, 'main_video') }}</template>
          </el-table-column>
          <el-table-column label="详情视频" width="90" align="center">
            <template #default="{ row }">{{ resourceCountText(row, 'detail_video') }}</template>
          </el-table-column>
          <el-table-column label="失败原因" min-width="160" show-overflow-tooltip>
            <template #default="{ row }">
              <span v-if="row.status === 'failed'" class="error-text">
                {{ row.error || '抓取失败' }}
              </span>
              <span v-else class="muted">—</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="200" align="center" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" @click.stop="openProduct(row)">预览</el-button>
              <el-button
                link
                type="success"
                :loading="downloadingId === row.id"
                @click.stop="downloadProduct(row)"
              >
                下载
              </el-button>
              <el-button
                v-if="row.status === 'failed'"
                link
                type="danger"
                :loading="retryingId === row.id"
                @click.stop="retryProduct(row)"
              >
                重试
              </el-button>
            </template>
          </el-table-column>
          <template #empty>
            <el-empty description="暂无商品" :image-size="70" />
          </template>
        </el-table>

        <div class="pagination-wrap">
          <el-pagination
            background
            layout="total, prev, pager, next"
            :total="productsTotal"
            :page-size="productsPageSize"
            :current-page="productsPage"
            @current-change="onProductsPageChange"
          />
        </div>
      </el-card>

      <!-- 日志流（SSE） -->
      <el-card shadow="always" class="log-card">
        <template #header><span>实时日志</span></template>
        <LogStream :task-id="Number(taskId)" />
      </el-card>
    </template>

    <el-empty v-else-if="!pageLoading" description="任务不存在或已被删除">
      <el-button type="primary" @click="$router.push('/')">返回列表</el-button>
    </el-empty>

    <!-- 商品详情弹窗 -->
    <ProductDialog v-model="dialogVisible" :product-id="activeProductId" />
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import ProgressPanel from '../components/ProgressPanel.vue'
import LogStream from '../components/LogStream.vue'
import ProductDialog from '../components/ProductDialog.vue'
import {
  fetchTask,
  fetchTaskProducts,
  startTask,
  pauseTask,
  cancelTask,
  resumeTask,
  retryProduct as apiRetryProduct,
  downloadTaskZip,
  downloadProductZip,
  getErrorMessage
} from '../api'
import {
  TASK_STATUS_MAP,
  PRODUCT_STATUS_MAP,
  TASK_ACTIVE_STATUSES,
  formatTime,
  resourceCountText,
  downloadBlob
} from '../utils'

const route = useRoute()
const router = useRouter()
const taskId = route.params.id

const task = ref(null)
const pageLoading = ref(false)
const acting = ref(false)
const downloading = ref(false)

const products = ref([])
const productsTotal = ref(0)
const productsPage = ref(1)
const productsPageSize = ref(20)
const productsLoading = ref(false)
const statusFilter = ref('')
const retryingId = ref(null)
const downloadingId = ref(null)

const dialogVisible = ref(false)
const activeProductId = ref(null)

let pollTimer = null
let polling = false

/* ------------------------------ 任务 ------------------------------ */

const taskStatusInfo = computed(() => {
  const s = task.value?.status
  return TASK_STATUS_MAP[s] || { text: s || '-', type: 'info' }
})

const downloadDisabled = computed(() => {
  const s = task.value?.status
  return s === 'running' || s === 'pending'
})

async function loadTask() {
  try {
    const data = await fetchTask(taskId)
    task.value = data
  } catch (e) {
    if (e.response?.status === 404) {
      task.value = null
      stopPolling()
    }
  }
}

async function loadProducts() {
  productsLoading.value = true
  try {
    const params = { page: productsPage.value, page_size: productsPageSize.value }
    if (statusFilter.value) params.status = statusFilter.value
    const data = await fetchTaskProducts(taskId, params)
    products.value = data.items || []
    productsTotal.value = data.total ?? 0
  } catch (e) {
    /* 拦截器已提示 */
  } finally {
    productsLoading.value = false
  }
}

/* ------------------------------ 轮询 ------------------------------ */

async function refresh() {
  if (polling) return
  polling = true
  try {
    await Promise.all([loadTask(), loadProducts()])
  } finally {
    polling = false
  }
}

function startPolling() {
  stopPolling()
  pollTimer = setInterval(refresh, 3000)
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

watch(
  () => task.value?.status,
  (status) => {
    if (TASK_ACTIVE_STATUSES.includes(status)) {
      startPolling()
    } else {
      stopPolling()
      // 终态后仅刷新一次商品列表，保证失败/成功状态最新
      if (status) loadProducts()
    }
  }
)

/* ------------------------------ 操作 ------------------------------ */

async function doAction(action) {
  acting.value = true
  try {
    const map = { start: startTask, pause: pauseTask, cancel: cancelTask, resume: resumeTask }
    await map[action](taskId)
    const tips = {
      start: '任务已开始运行',
      pause: '任务已暂停',
      cancel: '任务已取消',
      resume: '任务已续跑'
    }
    ElMessage.success(tips[action])
    await refresh()
  } catch (e) {
    /* 拦截器已提示 */
  } finally {
    acting.value = false
  }
}

async function downloadZip() {
  downloading.value = true
  try {
    const blob = await downloadTaskZip(taskId)
    if (blob && blob.size > 0) {
      downloadBlob(blob, `task_${taskId}_download.zip`)
      ElMessage.success('打包下载已开始')
    } else {
      ElMessage.warning('下载内容为空，可能无可用资源')
    }
  } catch (e) {
    if (e.response?.status === 409) {
      ElMessage.warning('任务仍在运行中，请等待结束后再打包下载')
    } else {
      ElMessage.error(getErrorMessage(e, '打包下载失败，请稍后重试'))
    }
  } finally {
    downloading.value = false
  }
}

/* ------------------------------ 商品 ------------------------------ */

function productStatusInfo(status) {
  return PRODUCT_STATUS_MAP[status] || { text: status || '-', type: 'info' }
}

function openProduct(row) {
  activeProductId.value = row.id
  dialogVisible.value = true
}

async function retryProduct(row) {
  retryingId.value = row.id
  try {
    await apiRetryProduct(row.id)
    ElMessage.success(`商品 ${row.product_id} 重试已发起`)
    await loadProducts()
  } catch (e) {
    /* 拦截器已提示 */
  } finally {
    retryingId.value = null
  }
}

/** 打包下载该商品选中的资源（后端仅打包 selected=1 的资源） */
async function downloadProduct(row) {
  downloadingId.value = row.id
  try {
    const blob = await downloadProductZip(row.id)
    if (blob && blob.size > 0) {
      downloadBlob(blob, `product_${row.product_id}_download.zip`)
      ElMessage.success(`商品 ${row.product_id} 选中资源已打包下载`)
    } else {
      ElMessage.warning(`商品 ${row.product_id} 没有选中的可用资源`)
    }
  } catch (e) {
    if (e.response?.status === 409) {
      ElMessage.warning('商品仍在抓取中，请稍后再试')
    } else {
      ElMessage.error(getErrorMessage(e, '打包下载失败，请稍后重试'))
    }
  } finally {
    downloadingId.value = null
  }
}

function onFilterChange() {
  productsPage.value = 1
  loadProducts()
}

function onProductsPageChange(p) {
  productsPage.value = p
  loadProducts()
}

/* ------------------------------ 生命周期 ------------------------------ */

onMounted(async () => {
  pageLoading.value = true
  await Promise.all([loadTask(), loadProducts()])
  pageLoading.value = false
  // 未终态时启动轮询
  if (task.value && TASK_ACTIVE_STATUSES.includes(task.value.status)) {
    startPolling()
  }
})

onBeforeUnmount(() => {
  stopPolling()
})
</script>

<style scoped>
.task-detail-view {
  max-width: 1200px;
  margin: 0 auto;
}

.page-header {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin-bottom: 16px;
}

.header-info {
  flex: 1;
}

.page-title {
  margin: 0 0 6px;
  font-size: 20px;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 10px;
}

.header-meta {
  font-size: 13px;
  color: #909399;
}

.status-tag {
  flex-shrink: 0;
}

.action-card,
.products-card,
.log-card {
  margin-bottom: 0;
}

.action-bar {
  display: flex;
  align-items: center;
  gap: 12px;
}

.download-tip {
  font-size: 12px;
  color: #c0c4cc;
}

.card-header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px;
}

.products-table {
  cursor: pointer;
}

.title-failed {
  color: #f56c6c;
}

.error-text {
  color: #f56c6c;
  font-size: 12px;
}

.muted {
  color: #c0c4cc;
}

.pagination-wrap {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}
</style>
