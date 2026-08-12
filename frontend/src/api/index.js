import axios from 'axios'
import { ElMessage } from 'element-plus'

/**
 * axios 统一封装：
 * - baseURL 为空，开发环境走 Vite 代理 /api -> http://127.0.0.1:8000
 * - 响应拦截器直接返回 data，错误统一 ElMessage 提示
 */
const http = axios.create({
  baseURL: '',
  timeout: 60000
})

http.interceptors.response.use(
  (response) => response.data,
  (error) => {
    // 允许调用方自行处理错误（如下载 409 需要自定义提示）
    if (error.config?.skipErrorToast) return Promise.reject(error)
    const status = error.response?.status
    const detail = error.response?.data?.detail
    let msg = ''
    if (status && detail) {
      msg = typeof detail === 'string' ? detail : JSON.stringify(detail)
    } else if (status === 409) {
      msg = '任务运行中，暂不可执行该操作'
    } else if (error.code === 'ECONNABORTED') {
      msg = '请求超时，请稍后重试'
    } else if (!error.response) {
      msg = '网络异常，无法连接后端服务'
    } else {
      msg = error.message || '请求失败'
    }
    if (msg) ElMessage.error(msg)
    return Promise.reject(error)
  }
)

/** 统一解析后端 detail 错误信息（供调用方 catch 后取用） */
export function getErrorMessage(err, fallback = '操作失败') {
  const detail = err?.response?.data?.detail
  if (detail) return typeof detail === 'string' ? detail : JSON.stringify(detail)
  return fallback
}

/* ------------------------------ 任务 ------------------------------ */

/** 创建任务：multipart(file, name, rate_limit, concurrency) */
export function createTask(formData) {
  return http.post('/api/tasks', formData, {
    headers: { 'Content-Type': 'multipart/form-data' }
  })
}

/** 解析 URL 列表文件：multipart file -> {total, invalid, product_ids[]} */
export function parseTaskFile(file) {
  const formData = new FormData()
  formData.append('file', file)
  return http.post('/api/tasks/parse', formData, {
    headers: { 'Content-Type': 'multipart/form-data' }
  })
}

/** 任务列表（分页） */
export function fetchTasks(page = 1, pageSize = 20) {
  return http.get('/api/tasks', { params: { page, page_size: pageSize } })
}

/** 任务详情 + 聚合进度 */
export function fetchTask(id) {
  return http.get(`/api/tasks/${id}`)
}

/** 任务操作 */
export const startTask = (id) => http.post(`/api/tasks/${id}/start`)
export const pauseTask = (id) => http.post(`/api/tasks/${id}/pause`)
export const cancelTask = (id) => http.post(`/api/tasks/${id}/cancel`)
export const resumeTask = (id) => http.post(`/api/tasks/${id}/resume`)

/** 任务商品列表（分页 + 状态过滤） */
export function fetchTaskProducts(id, params = {}) {
  return http.get(`/api/tasks/${id}/products`, { params })
}

/** 打包下载全任务 zip（运行中后端返回 409，调用方自行提示） */
export async function downloadTaskZip(id) {
  const blob = await http.get(`/api/tasks/${id}/download`, {
    responseType: 'blob',
    skipErrorToast: true
  })
  return blob
}

/** 单商品打包下载 zip */
export async function downloadProductZip(id) {
  const blob = await http.get(`/api/products/${id}/download`, {
    responseType: 'blob',
    skipErrorToast: true
  })
  return blob
}

/* ------------------------------ 商品 ------------------------------ */

/** 单商品详情（含 resources 列表） */
export function fetchProduct(id) {
  return http.get(`/api/products/${id}`)
}

/** 重试单个失败商品 */
export function retryProduct(id) {
  return http.post(`/api/products/${id}/retry`)
}

export default http
