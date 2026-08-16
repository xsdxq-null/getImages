<template>
  <div class="create-task-view">
    <div class="page-header">
      <el-button link @click="$router.back()">← 返回</el-button>
      <h2 class="page-title">创建任务</h2>
    </div>

    <el-row :gutter="16">
      <el-col :xs="24" :md="14">
        <el-card shadow="never">
          <template #header>
            <span>① 添加 URL 列表（上传文件 或 直接输入）</span>
          </template>

          <el-radio-group v-model="inputMode" class="input-mode">
            <el-radio-button value="file">上传文件</el-radio-button>
            <el-radio-button value="input">手动输入</el-radio-button>
          </el-radio-group>

          <el-upload
            v-if="inputMode === 'file'"
            drag
            :auto-upload="false"
            :limit="1"
            accept=".txt,.csv,text/plain,text/csv"
            :on-change="onFileChange"
            :on-exceed="onExceed"
            :on-remove="onFileRemove"
            :file-list="fileList"
            class="upload-box"
          >
            <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
            <div class="el-upload__text">将文件拖到此处，或 <em>点击上传</em></div>
            <template #tip>
              <div class="el-upload__tip">
                txt：每行一个商品详情页 URL；csv：需包含 url 列。系统将自动去重并剔除非法链接。
              </div>
            </template>
          </el-upload>

          <!-- 手动输入：el-input + el-tag 标签（回车添加、粘贴多行、可单独删除重复项） -->
          <div v-else class="input-tags">
            <el-input
              v-model="tagInput"
              placeholder="输入商品详情页 URL 后按回车添加，支持粘贴多行"
              clearable
              class="tag-input"
              @keyup.enter="addTagsFromInput"
              @paste="onTagPaste"
            />
            <div v-if="urlTags.length" class="tag-list">
              <el-tag
                v-for="t in urlTags"
                :key="t.key"
                closable
                type="info"
                class="url-tag"
                @close="removeTag(t.key)"
              >
                {{ t.value }}
              </el-tag>
            </div>
            <div class="input-tip">
              回车生成标签，可粘贴多行（每行一个）；重复 URL 可分别添加、单独删除；创建任务时自动去重并剔除非法链接。
            </div>
          </div>

          <!-- 解析结果 -->
          <div v-if="parseResult" class="parse-result">
            <el-alert
              :title="parseAlertTitle"
              :type="parseResult.total > 0 ? 'success' : 'warning'"
              :closable="false"
              show-icon
            />
            <div v-if="parseResult.invalid && parseResult.invalid.length" class="invalid-tip">
              <span class="invalid-label">已剔除 {{ parseResult.invalid.length }} 条非法/重复链接：</span>
              <el-tooltip placement="top" :content="parseResult.invalid.join('\n')">
                <el-link type="warning" :underline="false" class="invalid-more">
                  查看详情
                </el-link>
              </el-tooltip>
            </div>
          </div>
        </el-card>
      </el-col>

      <el-col :xs="24" :md="10">
        <el-card shadow="never">
          <template #header>
            <span>② 任务参数</span>
          </template>
          <el-form
            ref="formRef"
            :model="form"
            :rules="rules"
            label-width="100px"
            label-position="left"
          >
            <el-form-item label="任务名称" prop="name">
              <el-input
                v-model="form.name"
                placeholder="留空则自动生成（如 任务-20260618-120000）"
                maxlength="100"
                show-word-limit
              />
            </el-form-item>
            <el-form-item label="限速" prop="rate_limit">
              <el-input-number
                v-model="form.rate_limit"
                :min="0.5"
                :max="60"
                :step="0.5"
                :precision="1"
                controls-position="right"
              />
              <span class="unit">秒/请求</span>
              <div class="form-tip">默认 2.0 秒/请求，建议 ≥1 秒以合规抓取</div>
            </el-form-item>
            <el-form-item label="并发数" prop="concurrency">
              <el-input-number
                v-model="form.concurrency"
                :min="1"
                :max="10"
                controls-position="right"
              />
              <div class="form-tip">默认 2，建议 1–3</div>
            </el-form-item>
            <el-form-item>
              <el-button
                type="primary"
                :loading="submitting"
                :disabled="!currentFile || !parseResult || parseResult.total <= 0"
                @click="submit"
              >
                创建并运行任务
              </el-button>
              <span v-if="!currentFile" class="form-tip">请先上传文件</span>
            </el-form-item>
          </el-form>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { UploadFilled } from '@element-plus/icons-vue'
import { createTask, parseTaskFile, getErrorMessage } from '../api'

const router = useRouter()

const fileList = ref([])
const currentFile = ref(null)
const parseResult = ref(null)
const parseLoading = ref(false)
const submitting = ref(false)
const inputMode = ref('input')
const urlTags = ref([])
const tagInput = ref('')
let tagKeySeq = 0

/** 回车/输入添加标签：按行拆分（含粘贴换行），每项独立 key，可重复添加 */
function addTagsFromInput() {
  const text = String(tagInput.value || '').trim()
  if (!text) return
  for (const line of text.split(/\r?\n/)) {
    const u = line.trim()
    if (!u) continue
    urlTags.value.push({ key: ++tagKeySeq, value: u })
  }
  tagInput.value = ''
}

/** 粘贴多行：等粘贴完成后统一解析 */
function onTagPaste(e) {
  // 延迟到剪贴板内容进入输入框后处理
  setTimeout(() => {
    const lines = String(tagInput.value || '').split(/\r?\n/)
    if (lines.length > 1) {
      for (const line of lines) {
        const u = line.trim()
        if (u) urlTags.value.push({ key: ++tagKeySeq, value: u })
      }
      tagInput.value = ''
    }
  }, 0)
}

/** 删除单个标签（按唯一 key，重复项可单独删） */
function removeTag(key) {
  urlTags.value = urlTags.value.filter((t) => t.key !== key)
}

const form = ref({
  name: '',
  rate_limit: 2.0,
  concurrency: 2
})

const rules = {
  rate_limit: [{ required: true, message: '请设置限速（秒/请求）', trigger: 'blur' }],
  concurrency: [{ required: true, message: '请设置并发数', trigger: 'blur' }]
}

const parseAlertTitle = computed(() => {
  if (!parseResult.value) return ''
  const { total, invalid } = parseResult.value
  if (total <= 0) {
    return `未解析到有效商品链接${invalid.length ? `（${invalid.length} 条被剔除）` : ''}，无法创建任务`
  }
  return `解析成功：共 ${total} 件有效商品${invalid.length ? `，剔除 ${invalid.length} 条非法/重复链接` : ''}`
})

function onExceed() {
  ElMessage.warning('仅支持上传一个文件，请先移除已选文件')
}

function onFileRemove() {
  currentFile.value = null
  parseResult.value = null
}

async function onFileChange(file, files) {
  const f = file.raw || file
  if (!f) return
  currentFile.value = f
  parseResult.value = null
  parseLoading.value = true

  // 1) 前端本地解析，作为降级提示
  const local = await parseLocally(f)
  // 2) 调用后端 /api/tasks/parse 获取权威校验结果
  try {
    const data = await parseTaskFile(f)
    parseResult.value = {
      total: data.total ?? 0,
      invalid: Array.isArray(data.invalid) ? data.invalid : [],
      source: 'backend'
    }
  } catch (e) {
    // 后端未实现 parse 端点（404）或不可用：降级用前端解析结果
    parseResult.value = {
      total: local.total,
      invalid: local.invalid,
      source: 'local'
    }
    ElMessage.warning('后端解析接口不可用，已按前端解析结果展示，最终以创建任务时的校验为准')
  } finally {
    parseLoading.value = false
  }
}

/** 前端解析：txt 每行一个 URL；csv 找 url 列。统计有效数与剔除项 */
function parseLocally(file) {
  return new Promise((resolve) => {
    const reader = new FileReader()
    reader.onload = () => {
      let text = String(reader.result || '')
      text = text.replace(/^\uFEFF/, '') // 剥离 UTF-8 BOM（Windows 记事本等生成）
      const isCsv = /\.csv$/i.test(file.name)
      const lines = text
        .split(/\r?\n/)
        .map((s) => s.trim())
        .filter(Boolean)
      let candidates = lines
      if (isCsv && lines.length) {
        const header = lines[0].split(',').map((s) => s.trim().toLowerCase())
        const urlIdx = header.indexOf('url')
        if (urlIdx >= 0) {
          candidates = lines
            .slice(1)
            .map((l) => {
              const cells = splitCSVLine(l)
              return (cells[urlIdx] || '').trim()
            })
            .filter(Boolean)
        }
      }
      const seen = new Set()
      const valid = []
      const invalid = []
      for (const u of candidates) {
        if (isValidUrl(u) && !seen.has(u)) {
          seen.add(u)
          valid.push(u)
        } else {
          invalid.push(u)
        }
      }
      resolve({ total: valid.length, invalid })
    }
    reader.onerror = () => resolve({ total: 0, invalid: [] })
    reader.readAsText(file)
  })
}

function splitCSVLine(line) {
  const cells = []
  let cur = ''
  let inQuote = false
  for (let i = 0; i < line.length; i++) {
    const ch = line[i]
    if (ch === '"') {
      if (inQuote && line[i + 1] === '"') {
        cur += '"'
        i++
      } else {
        inQuote = !inQuote
      }
    } else if (ch === ',' && !inQuote) {
      cells.push(cur)
      cur = ''
    } else {
      cur += ch
    }
  }
  cells.push(cur)
  return cells.map((s) => s.trim())
}

/** URL 合法性：http(s) 开头且末段含至少 5 位数字（商品 ID，兼容 _ID.html 格式） */
function isValidUrl(u) {
  if (!/^https?:\/\//i.test(u)) return false
  return /(\d{5,})(?:[./?#]|$)/.test(u)
}

async function submit() {
  let file = currentFile.value
  if (!file && inputMode.value === 'input') {
    // 手动输入：把标签列表组装成 txt 文件（后端统一解析/去重/校验）
    const lines = (urlTags.value || []).map((t) => String(t.value || '').trim()).filter(Boolean)
    if (lines.length === 0) {
      ElMessage.warning('请先输入至少一个商品 URL')
      return
    }
    file = new File([lines.join('\n')], 'urls_input.txt', { type: 'text/plain' })
  }
  if (!file) {
    ElMessage.warning('请先上传 URL 列表文件或输入商品 URL')
    return
  }
  submitting.value = true
  try {
    const formData = new FormData()
    formData.append('file', file)
    formData.append('name', form.value.name || autoName())
    formData.append('rate_limit', String(form.value.rate_limit))
    formData.append('concurrency', String(form.value.concurrency))
    const data = await createTask(formData)
    ElMessage.success(`任务创建成功，共 ${data.total ?? '-'} 件商品`)
    router.push(`/tasks/${data.id}`)
  } catch (e) {
    const msg = getErrorMessage(e, '任务创建失败')
    ElMessageBox.alert(msg, '创建失败', { type: 'error' })
  } finally {
    submitting.value = false
  }
}

function autoName() {
  const d = new Date()
  const pad = (n) => String(n).padStart(2, '0')
  return `任务-${d.getFullYear()}${pad(d.getMonth() + 1)}${pad(d.getDate())}-${pad(d.getHours())}${pad(d.getMinutes())}${pad(d.getSeconds())}`
}
</script>

<style scoped>
.create-task-view {
  max-width: 1100px;
  margin: 0 auto;
}

.page-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 16px;
}

.page-title {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
}

.upload-box :deep(.el-upload-dragger) {
  padding: 30px 20px;
}

.input-mode {
  margin-bottom: 14px;
}

.input-tags {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.tag-input {
  width: 100%;
}

.tag-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  max-height: 180px;
  overflow-y: auto;
}

.url-tag {
  max-width: 100%;
}

.url-tag :deep(.el-tag__content) {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.input-tip {
  font-size: 12px;
  color: #909399;
}

.parse-result {
  margin-top: 16px;
}

.invalid-tip {
  margin-top: 10px;
  font-size: 13px;
  color: #909399;
  display: flex;
  align-items: center;
  gap: 6px;
}

.invalid-label {
  flex-shrink: 0;
}

.unit {
  margin-left: 8px;
  color: #909399;
  font-size: 13px;
}

.form-tip {
  width: 100%;
  margin-top: 4px;
  font-size: 12px;
  color: #c0c4cc;
  line-height: 1.5;
}
</style>
