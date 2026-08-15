<template>
  <div class="media-preview">
    <!-- 图片类资源 -->
    <template v-if="isImage">
      <div v-if="items.length" class="media-grid">
        <div v-for="(item, i) in items" :key="i" class="media-cell" :class="{ selected: isSelected(item.id) }" @click="toggleSelect(item.id)">
          <el-checkbox
            v-model="selectedSet"
            :value="item.id"
            class="media-check"
            @click.stop
            @change="onChange"
          />
          <el-image
            :src="displayUrl(item)"
            fit="cover"
            class="media-thumb"
            lazy
          >
            <template #error>
              <div class="thumb-error">加载失败</div>
            </template>
          </el-image>
          <!-- 中间眼睛：点击预览大图（不触发选中切换）；复用 el-button circle -->
          <el-button
            circle
            class="media-eye"
            title="预览大图"
            @click.stop="openViewer(i)"
          >
            <el-icon :size="18"><View /></el-icon>
          </el-button>
        </div>
      </div>
      <el-empty v-else description="暂无该类资源" :image-size="60" />
    </template>

    <!-- 视频类资源 -->
    <template v-else>
      <div v-if="items.length" class="media-list">
        <div v-for="(item, i) in items" :key="i" class="video-item">
          <div class="video-row">
            <el-checkbox
              v-model="selectedSet"
              :value="item.id"
              class="media-check-inline"
              @change="onChange"
            />
            <div class="video-desc">
              视频 {{ i + 1 }}
              <el-tag v-if="item.status === 'failed'" type="danger" size="small">失败</el-tag>
            </div>
          </div>
          <video :src="displayUrl(item)" controls preload="metadata" class="media-video" />
        </div>
      </div>
      <el-empty v-else description="暂无该类资源" :image-size="60" />
    </template>
  </div>

  <!-- 大图预览（点击眼睛按钮打开） -->
  <el-image-viewer
    v-if="viewerVisible"
    :url-list="previewUrls"
    :initial-index="previewIndex"
    teleported
    @close="viewerVisible = false"
  />
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { View } from '@element-plus/icons-vue'

const props = defineProps({
  /** 资源类别：main_image / detail_image / main_video / detail_video */
  kind: { type: String, required: true },
  /** 资源列表 [{id, url, file_path, status, ...}] */
  resources: { type: Array, default: () => [] },
  /** 选中的资源 id 集合（v-model） */
  selectedIds: { type: Array, default: () => [] }
})

const emit = defineEmits(['update:selectedIds'])

const isImage = computed(() => props.kind === 'main_image' || props.kind === 'detail_image')

const items = computed(() => props.resources || [])

const selectedSet = ref([...props.selectedIds])

watch(
  () => props.selectedIds,
  (ids) => {
    selectedSet.value = [...ids]
  }
)

function onChange() {
  emit('update:selectedIds', [...selectedSet.value])
}

function isSelected(id) {
  return selectedSet.value.includes(id)
}

/** 点击图片（非眼睛按钮区域）：切换选中状态 */
function toggleSelect(id) {
  const idx = selectedSet.value.indexOf(id)
  if (idx >= 0) {
    selectedSet.value.splice(idx, 1)
  } else {
    selectedSet.value.push(id)
  }
  onChange()
}

/* ------------------------------ 大图预览 ------------------------------ */

const viewerVisible = ref(false)
const previewIndex = ref(0)

const previewUrls = computed(() => items.value.map((x) => displayUrl(x)))

function openViewer(i) {
  previewIndex.value = i
  viewerVisible.value = true
}

/** 展示 URL：优先原始 url，缺失时用 file_path（FastAPI 静态托管时可直接访问） */
function displayUrl(item) {
  if (!item) return ''
  if (item.url) return item.url
  if (item.file_path) {
    const p = item.file_path.replace(/\\/g, '/')
    return p.startsWith('/') ? p : `/${p}`
  }
  return ''
}
</script>

<style scoped>
.media-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  gap: 12px;
}

.media-cell {
  position: relative;
}

/* 紧凑多选框：去掉空白 label 占位与背景块，紧贴图片左上角 */
.media-check {
  position: absolute;
  top: 6px;
  left: 6px;
  z-index: 2;
  margin: 0;
  padding: 0;
}

.media-check :deep(.el-checkbox__label) {
  display: none;
}

.media-check :deep(.el-checkbox__input) {
  margin-right: 0;
}

/* 视频行内多选框：同样去空白 label 占位，但保持文档流内 */
.media-check-inline {
  margin: 0;
  padding: 0;
  flex-shrink: 0;
}

.media-check-inline :deep(.el-checkbox__label) {
  display: none;
}

.media-check-inline :deep(.el-checkbox__input) {
  margin-right: 0;
}

/* 选中状态：图片边框高亮 */
.media-cell.selected .media-thumb {
  border-color: var(--el-color-primary);
  border-width: 2px;
  box-shadow: 0 0 0 1px var(--el-color-primary);
}

/* 中间眼睛按钮（el-button circle）：点击预览大图（不触发选中切换） */
.media-eye {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  background: rgba(0, 0, 0, 0.45);
  border-color: transparent;
  color: #fff;
  opacity: 0.85;
}

.media-eye:hover,
.media-eye:focus {
  background: rgba(0, 0, 0, 0.65);
  border-color: transparent;
  color: #fff;
  opacity: 1;
}

.media-cell .media-thumb {
  cursor: pointer;
}

.media-thumb {
  width: 100%;
  height: 120px;
  border-radius: 6px;
  border: 1px solid #e4e7ed;
  background: #f5f7fa;
  cursor: zoom-in;
}

.thumb-error {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #909399;
  font-size: 12px;
}

.media-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.video-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.video-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.media-video {
  width: 100%;
  max-height: 320px;
  border-radius: 6px;
  background: #000;
}

.video-desc {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: #606266;
}
</style>
