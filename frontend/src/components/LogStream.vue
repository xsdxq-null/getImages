<template>
  <div class="log-stream">
    <div class="log-toolbar">
      <el-radio-group v-model="levelFilter" size="small">
        <el-radio-button value="all">全部</el-radio-button>
        <el-radio-button value="info">INFO</el-radio-button>
        <el-radio-button value="warn">WARN</el-radio-button>
        <el-radio-button value="error">ERROR</el-radio-button>
      </el-radio-group>
      <el-switch v-model="autoScroll" active-text="自动滚动" size="small" />
      <el-button size="small" @click="clearLogs">清空</el-button>
      <span v-if="!connected" class="conn-status">连接断开，重连中…</span>
      <span v-else class="conn-status ok">● 实时连接</span>
    </div>

    <el-scrollbar
      ref="scrollbarRef"
      class="log-scroll"
      :height="260"
      @scroll="onScroll"
    >
      <div class="log-body">
        <div
          v-for="(log, i) in filteredLogs"
          :key="i"
          class="log-line"
        >
          <span class="log-ts">{{ log.ts }}</span>
          <span class="log-level" :class="`lv-${log.level}`">{{ log.level }}</span>
          <span v-if="log.product_id" class="log-pid">[{{ log.product_id }}]</span>
          <span class="log-msg">{{ log.message }}</span>
        </div>
        <div v-if="!logs.length" class="log-empty">暂无日志…</div>
      </div>
    </el-scrollbar>
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick, onMounted, onBeforeUnmount } from 'vue'
import { formatTime } from '../utils'

const props = defineProps({
  taskId: { type: Number, required: true }
})

const logs = ref([])
const levelFilter = ref('all')
const autoScroll = ref(true)
const connected = ref(false)

const scrollbarRef = ref(null)
let es = null
let atBottom = true
const MAX_LOGS = 2000

const filteredLogs = computed(() => {
  if (levelFilter.value === 'all') return logs.value
  return logs.value.filter((l) => l.level === levelFilter.value)
})

/** 归一化日志级别：warning -> warn，并统一小写 */
function normalizeLevel(level) {
  const s = String(level || 'info').toLowerCase()
  if (s === 'warning' || s === 'warn') return 'warn'
  if (s === 'error' || s === 'err' || s === 'critical') return 'error'
  return 'info'
}

function pushLog(raw) {
  let obj
  try {
    obj = JSON.parse(raw)
  } catch (e) {
    return
  }
  if (!obj || obj.message == null) return
  const tsRaw = obj.ts
  logs.value.push({
    ts: tsRaw ? formatTime(tsRaw) : '-',
    level: normalizeLevel(obj.level),
    product_id: obj.product_id || null,
    message: String(obj.message)
  })
  if (logs.value.length > MAX_LOGS) {
    logs.value.splice(0, logs.value.length - MAX_LOGS)
  }
  scrollToBottomIfNeeded()
}

function scrollToBottomIfNeeded() {
  if (!autoScroll.value || !atBottom) return
  nextTick(() => {
    const wrap = scrollbarRef.value?.wrapRef
    if (wrap) wrap.scrollTop = wrap.scrollHeight
  })
}

function onScroll() {
  const wrap = scrollbarRef.value?.wrapRef
  if (!wrap) return
  const dist = wrap.scrollHeight - wrap.scrollTop - wrap.clientHeight
  atBottom = dist < 40
  // 用户滚回底部时自动恢复跟随
  if (atBottom && !autoScroll.value) autoScroll.value = true
}

watch(autoScroll, (v) => {
  if (v) scrollToBottomIfNeeded()
})

function clearLogs() {
  logs.value = []
}

function connect() {
  if (!props.taskId) return
  es = new EventSource(`/api/tasks/${props.taskId}/logs`)

  // 默认 message 事件；兼容命名事件 'log'
  es.onopen = () => {
    connected.value = true
  }
  es.onmessage = (event) => pushLog(event.data)
  es.addEventListener('log', (event) => pushLog(event.data))
  es.onerror = () => {
    connected.value = false
    // EventSource 会自动重连，此处仅更新状态提示
  }
}

onMounted(connect)

onBeforeUnmount(() => {
  if (es) {
    es.close()
    es = null
  }
})
</script>

<style scoped>
.log-stream {
  width: 100%;
}

.log-toolbar {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}

.conn-status {
  margin-left: auto;
  font-size: 12px;
  color: #f56c6c;
}

.conn-status.ok {
  color: #67c23a;
}

.log-scroll {
  background: #1e1e1e;
  border-radius: 6px;
  padding: 4px 0;
}

.log-body {
  padding: 8px 12px;
  font-family: Consolas, Monaco, 'Courier New', monospace;
  font-size: 12px;
  line-height: 1.7;
}

.log-line {
  display: flex;
  gap: 8px;
  white-space: pre-wrap;
  word-break: break-all;
}

.log-ts {
  color: #8a8f98;
  flex-shrink: 0;
}

.log-level {
  flex-shrink: 0;
  min-width: 42px;
  text-align: center;
  border-radius: 3px;
  font-weight: 600;
}

.lv-info {
  color: #6cb6ff;
}

.lv-warn {
  color: #e6a23c;
}

.lv-error {
  color: #f56c6c;
}

.log-pid {
  color: #c792ea;
  flex-shrink: 0;
}

.log-msg {
  color: #d4d7dd;
}

.log-empty {
  color: #6b6f76;
  padding: 8px 0;
}
</style>
