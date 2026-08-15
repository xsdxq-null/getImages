<template>
  <el-dialog
    :model-value="modelValue"
    :title="dialogTitle"
    width="760px"
    top="6vh"
    destroy-on-close
    :close-on-click-modal="false"
    @update:model-value="$emit('update:modelValue', $event)"
  >
    <div v-loading="loading" class="product-dialog">
      <template v-if="product">
        <div class="product-info">
          <div class="info-row">
            <span class="info-label">商品 ID：</span>
            <b>{{ product.product_id }}</b>
            <el-tag :type="statusInfo.type" size="small" effect="light" class="info-tag">
              {{ statusInfo.text }}
            </el-tag>
          </div>
          <div class="info-row title-row">
            <span class="info-label">标题：</span>
            <span>{{ product.title || '（无标题）' }}</span>
          </div>
          <div v-if="product.status === 'failed' && product.error" class="info-row">
            <span class="info-label">失败原因：</span>
            <span class="error-text">{{ product.error }}</span>
          </div>
        </div>

        <el-tabs v-model="activeTab" class="resource-tabs">
          <el-tab-pane
            v-for="k in RESOURCE_KINDS"
            :key="k.key"
            :name="k.key"
            :label="`${k.label} (${countOf(k.key)})`"
          >
            <MediaPreview
              :kind="k.key"
              :resources="resourcesOf(k.key)"
              v-model:selected-ids="selectedIds"
            />
          </el-tab-pane>
        </el-tabs>

        <div class="selection-bar">
          <el-checkbox
            :model-value="allSelected"
            :indeterminate="partSelected"
            @change="toggleSelectAll"
          >
            全选（{{ selectedIds.length }}/{{ allResourceIds.length }}）
          </el-checkbox>
          <span class="selection-tip">仅勾选的资源会打包下载</span>
        </div>
      </template>
      <el-empty v-else-if="!loading" description="商品不存在或已删除" :image-size="70" />
    </div>

    <template #footer>
      <div v-if="product" class="dialog-footer">
        <el-button @click="$emit('update:modelValue', false)">关闭</el-button>
        <el-button
          type="success"
          :disabled="selectedIds.length === 0"
          :loading="downloading"
          @click="downloadProduct"
        >
          打包下载选中资源（{{ selectedIds.length }}）
        </el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import MediaPreview from './MediaPreview.vue'
import { fetchProduct, downloadProductZip, saveResourcesSelection, getErrorMessage } from '../api'
import { RESOURCE_KINDS, PRODUCT_STATUS_MAP, downloadBlob } from '../utils'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  productId: { type: Number, default: null }
})

const emit = defineEmits(['update:modelValue'])

const product = ref(null)
const loading = ref(false)
const downloading = ref(false)
const activeTab = ref('main_image')
const selectedIds = ref([])
let saveTimer = null

const dialogTitle = computed(() => {
  if (!product.value) return '商品详情'
  return `商品详情 · ${product.value.product_id || product.value.id || ''}`
})

const statusInfo = computed(() => {
  const s = product.value?.status
  return PRODUCT_STATUS_MAP[s] || { text: s || '-', type: 'info' }
})

function resourcesOf(kind) {
  if (!product.value?.resources) return []
  return product.value.resources.filter((r) => r.kind === kind)
}

function countOf(kind) {
  return resourcesOf(kind).length
}

const allResourceIds = computed(() => {
  if (!product.value?.resources) return []
  return product.value.resources.map((r) => r.id)
})

const allSelected = computed(
  () => allResourceIds.value.length > 0 && selectedIds.value.length === allResourceIds.value.length
)

const partSelected = computed(
  () => selectedIds.value.length > 0 && !allSelected.value
)

/** 勾选变化：更新本地选中集合并防抖保存到后端 */
function persistSelection() {
  if (!product.value) return
  clearTimeout(saveTimer)
  saveTimer = setTimeout(async () => {
    try {
      await saveResourcesSelection(product.value.id, selectedIds.value)
    } catch (e) {
      ElMessage.error(getErrorMessage(e, '保存选中状态失败'))
    }
  }, 300)
}

function toggleSelectAll(checked) {
  selectedIds.value = checked ? [...allResourceIds.value] : []
  persistSelection()
}

/** 勾选变化（弹窗内 checkbox / 整图点击 / 全选）→ 防抖自动保存到后端 */
watch(
  () => selectedIds.value,
  () => {
    // load() 初始化选中状态时 loading=true，跳过（初始值无需回写）
    if (!loading.value && product.value) persistSelection()
  }
)

async function load() {
  if (!props.productId) return
  loading.value = true
  product.value = null
  activeTab.value = 'main_image'
  clearTimeout(saveTimer)
  try {
    product.value = await fetchProduct(props.productId)
    // 初始化选中状态：resources.selected=1 的 id
    selectedIds.value = (product.value.resources || [])
      .filter((r) => r.selected === 1)
      .map((r) => r.id)
  } catch (e) {
    /* 拦截器已提示 */
  } finally {
    loading.value = false
  }
}

async function downloadProduct() {
  if (!product.value) return
  if (selectedIds.value.length === 0) {
    ElMessage.warning('请先勾选要下载的资源')
    return
  }
  downloading.value = true
  try {
    const blob = await downloadProductZip(product.value.id)
    if (blob && blob.size > 0) {
      downloadBlob(blob, `product_${product.value.product_id}_download.zip`)
      ElMessage.success(`已打包下载选中的 ${selectedIds.value.length} 个资源`)
    } else {
      ElMessage.warning('选中的资源均无可用文件，请重新勾选')
    }
  } catch (e) {
    if (e.response?.status === 409) {
      ElMessage.warning('商品仍在抓取中，请稍后再试')
    } else {
      ElMessage.error(getErrorMessage(e, '打包下载失败，请稍后重试'))
    }
  } finally {
    downloading.value = false
  }
}

watch(
  () => props.modelValue,
  (visible) => {
    if (visible) {
      load()
    } else {
      clearTimeout(saveTimer)
    }
  }
)
</script>

<style scoped>
.product-dialog {
  min-height: 320px;
}

.product-info {
  background: #f5f7fa;
  border-radius: 6px;
  padding: 12px 16px;
  margin-bottom: 12px;
  font-size: 13px;
}

.info-row {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  margin-bottom: 6px;
  line-height: 1.6;
}

.info-row:last-child {
  margin-bottom: 0;
}

.info-label {
  color: #909399;
  flex-shrink: 0;
}

.info-tag {
  margin-left: 8px;
}

.title-row span:last-child {
  word-break: break-all;
}

.error-text {
  color: #f56c6c;
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
}

.selection-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 12px;
  padding: 8px 12px;
  background: #f5f7fa;
  border-radius: 6px;
  font-size: 13px;
}

.selection-tip {
  color: #909399;
  font-size: 12px;
}
</style>
