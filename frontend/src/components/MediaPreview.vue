<template>
  <div class="media-preview">
    <!-- 图片类资源 -->
    <template v-if="isImage">
      <div v-if="items.length" class="media-grid">
        <div v-for="(item, i) in items" :key="i" class="media-cell">
          <el-checkbox
            v-model="selectedSet"
            :value="item.id"
            class="media-check"
            @click.stop
            @change="onChange"
          />
          <el-image
            :src="displayUrl(item)"
            :preview-src-list="items.map((x) => displayUrl(x))"
            :initial-index="i"
            fit="cover"
            class="media-thumb"
            :preview-teleported="true"
            lazy
          >
            <template #error>
              <div class="thumb-error">加载失败</div>
            </template>
          </el-image>
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
</template>

<script setup>
import { ref, computed, watch } from 'vue'

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

const selectedSet = ref(new Set(props.selectedIds))

watch(
  () => props.selectedIds,
  (ids) => {
    selectedSet.value = new Set(ids)
  }
)

function onChange() {
  emit('update:selectedIds', [...selectedSet.value])
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

.media-check {
  position: absolute;
  top: 4px;
  left: 4px;
  z-index: 2;
  background: rgba(255, 255, 255, 0.85);
  border-radius: 4px;
  padding: 2px;
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
