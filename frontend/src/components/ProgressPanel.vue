<template>
  <el-card shadow="always" class="progress-panel">
    <div class="progress-main">
      <div class="progress-left">
        <el-progress
          :percentage="percentage"
          :status="progressStatus"
          :stroke-width="18"
          class="progress-bar"
        />
        <div class="progress-meta">
          <span>已完成 <b>{{ done }}</b> / <b>{{ total }}</b> 件商品</span>
          <span>成功率 <b :class="{ 'low-rate': successRate < 100 && total > 0 }">{{ successRate }}%</b></span>
          <span>失败 <b :class="{ 'fail-count': failed > 0 }">{{ failed }}</b></span>
        </div>
      </div>
      <div class="progress-right">
        <el-tag :type="statusInfo.type" effect="dark" size="large">
          {{ statusInfo.text }}
        </el-tag>
      </div>
    </div>
  </el-card>
</template>

<script setup>
import { computed } from 'vue'
import { TASK_STATUS_MAP, calcSuccessRate } from '../utils'

const props = defineProps({
  /** 任务对象（含 total/succeeded/failed/progress/status） */
  task: { type: Object, required: true }
})

const total = computed(() => props.task?.total ?? 0)
const done = computed(() => props.task?.succeeded ?? 0)
const failed = computed(() => props.task?.failed ?? 0)

/** 百分比：优先后端聚合 progress 字段，缺失时按完成数计算 */
const percentage = computed(() => {
  const p = props.task?.progress
  if (typeof p === 'number' && p >= 0) return Math.min(100, Math.round(p))
  if (!total.value) return 0
  return Math.round((done.value / total.value) * 100)
})

const successRate = computed(() => calcSuccessRate(total.value, done.value))

const statusInfo = computed(() => {
  const s = props.task?.status
  return TASK_STATUS_MAP[s] || { text: s || '-', type: 'info' }
})

/** 进度条状态：done 绿色、partial/cancelled 警告色、failed 红色 */
const progressStatus = computed(() => {
  const s = props.task?.status
  if (s === 'done') return 'success'
  if (s === 'partial') return 'warning'
  if (s === 'cancelled' && total.value > 0 && failed.value > 0) return 'exception'
  if (s === 'paused') return 'warning'
  return undefined
})
</script>

<style scoped>
.progress-panel {
  margin-bottom: 16px;
}

.progress-main {
  display: flex;
  align-items: center;
  gap: 24px;
}

.progress-left {
  flex: 1;
}

.progress-bar {
  margin-bottom: 8px;
}

.progress-meta {
  display: flex;
  gap: 24px;
  font-size: 13px;
  color: #606266;
}

.progress-meta b {
  color: #303133;
  font-size: 14px;
}

.progress-meta .low-rate {
  color: #e6a23c;
}

.progress-meta .fail-count {
  color: #f56c6c;
}

.progress-right {
  flex-shrink: 0;
}
</style>
