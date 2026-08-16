/** 公共常量与工具函数 */

/** 任务状态展示映射（key -> {text, type}） */
export const TASK_STATUS_MAP = {
  pending: { text: '待开始', type: 'info' },
  running: { text: '运行中', type: 'primary' },
  paused: { text: '已暂停', type: 'warning' },
  cancelled: { text: '已取消', type: 'info' },
  done: { text: '已完成', type: 'success' },
  partial: { text: '部分完成', type: 'warning' }
}

/** 商品状态展示映射 */
export const PRODUCT_STATUS_MAP = {
  pending: { text: '待处理', type: 'info' },
  fetching: { text: '抓取中', type: 'warning' },
  done: { text: '完成', type: 'success' },
  failed: { text: '失败', type: 'danger' }
}

/** 四类资源 */
export const RESOURCE_KINDS = [
  { key: 'main_image', label: '主图' },
  { key: 'detail_image', label: '详情图' },
  { key: 'main_video', label: '主图视频' },
  { key: 'detail_video', label: '详情视频' }
]

/** 任务处于运行/暂停等"未终态"（需要轮询；待开始的任务商品列表静态，无需自动刷新） */
export const TASK_ACTIVE_STATUSES = ['running', 'paused']

/** 任务是否已进入终态 */
export function isTaskFinal(status) {
  return ['cancelled', 'done', 'partial'].includes(status)
}

/** ISO 时间转本地字符串；空值返回 '-' */
export function formatTime(iso) {
  if (!iso) return '-'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  const pad = (n) => String(n).padStart(2, '0')
  return (
    `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ` +
    `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
  )
}

/** 成功率（0-100，保留 1 位小数；total 为 0 时返回 0） */
export function calcSuccessRate(total, succeeded) {
  if (!total) return 0
  return Math.round((succeeded / total) * 1000) / 10
}

/**
 * 读取商品行中某类资源的完成计数。
 * 兼容两种后端返回形态：
 *  - resource_counts: { main_image: {done, total, selected} }（对象/数组）
 *  - main_image_done / main_image_count 扁平字段
 * 有 selected 计数时返回 'selected/total'（下载选中的语义），否则返回 'done/total'
 */
export function resourceCountText(row, kind) {
  const rc = row && row.resource_counts
  if (rc && rc[kind] != null) {
    const c = rc[kind]
    if (typeof c === 'object' && c !== null) {
      const done = c.done ?? 0
      const total = c.total ?? 0
      if (c.selected != null) {
        const sel = c.selected ?? 0
        return total ? `${sel}/${total}` : `${sel}`
      }
      return total ? `${done}/${total}` : `${done}`
    }
    return String(c)
  }
  const done = row ? row[`${kind}_done`] ?? row[`${kind}_count`] ?? 0 : 0
  return String(done)
}

/** 触发浏览器下载（blob 数据） */
export function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}
