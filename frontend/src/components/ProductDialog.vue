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
            <MediaPreview :kind="k.key" :resources="resourcesOf(k.key)" />
          </el-tab-pane>
        </el-tabs>
      </template>
      <el-empty v-else-if="!loading" description="商品不存在或已删除" :image-size="70" />
    </div>

    <template #footer>
      <div v-if="product" class="dialog-footer">
        <el-button @click="$emit('update:modelValue', false)">关闭</el-button>
        <el-button
          type="success"
          :loading="downloading"
          @click="downloadProduct"
        >
          打包下载该商品
        </el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import MediaPreview from './MediaPreview.vue'
import { fetchProduct, downloadProductZip, getErrorMessage } from '../api'
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

async function load() {
  if (!props.productId) return
  loading.value = true
  product.value = null
  activeTab.value = 'main_image'
  try {
    product.value = await fetchProduct(props.productId)
  } catch (e) {
    /* 拦截器已提示 */
  } finally {
    loading.value = false
  }
}

async function downloadProduct() {
  if (!product.value) return
  downloading.value = true
  try {
    const blob = await downloadProductZip(product.value.id)
    if (blob && blob.size > 0) {
      downloadBlob(blob, `product_${product.value.product_id}_download.zip`)
      ElMessage.success('商品打包下载已开始')
    } else {
      ElMessage.warning('下载内容为空，可能无可用资源')
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
    if (visible) load()
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
</style>
