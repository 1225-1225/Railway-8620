<template>
  <div class="app-layout">
    <HistorySidebar
      :collapsed="sidebarCollapsed"
      :width="sidebarWidth"
      :loading="loadingSessions"
      :groups="sessionGroups"
      :active-thread-id="activeThreadId"
      @toggle="sidebarCollapsed = !sidebarCollapsed"
      @new-chat="startNewChat"
      @select-session="loadSession"
      @rename-session="renameSession"
      @delete-session="deleteSession"
    />
    <!-- 可拖拽分隔条：调整历史侧边栏宽度 -->
    <div
      v-show="!sidebarCollapsed"
      class="resize-handle"
      :class="{ dragging: isResizing }"
      role="separator"
      aria-orientation="vertical"
      aria-label="调整历史对话宽度"
      :aria-valuenow="sidebarWidth"
      :aria-valuemin="SIDEBAR_MIN"
      :aria-valuemax="SIDEBAR_MAX"
      tabindex="0"
      @mousedown="startResize"
      @keydown="onResizeKeydown"
      @dblclick="resetSidebarWidth"
    ></div>
    <div class="main-area">
      <header class="chat-header">
        <div class="header-left">
          <div class="logo">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <rect x="5" y="3" width="14" height="13" rx="3" />
            <path d="M5 9h14" />
            <circle cx="9" cy="12.5" r="1" fill="currentColor" stroke="none" />
            <circle cx="15" cy="12.5" r="1" fill="currentColor" stroke="none" />
            <path d="M8 16l-2 4M16 16l2 4M4 20h16" />
          </svg>
        </div>
          <div class="header-text">
            <h2>铁路历史专家 (流式版)</h2>
            <p class="online-status">已连接 · 实时流式输出</p>
          </div>
        </div>
        <div class="header-right">
          <button class="logout-btn" @click="logout">退出</button>
        </div>
    </header>

    <div class="chat-messages" ref="messageListRef">
      <div v-if="messages.length === 0" class="welcome-message">
        <div class="welcome-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M21 11.5a8.4 8.4 0 0 1-9 8.4 8.9 8.9 0 0 1-3.8-.9L3 20.5l1.4-4.2A8.4 8.4 0 0 1 3 11.5a8.4 8.4 0 0 1 9-8.4 8.4 8.4 0 0 1 9 8.4z" />
          </svg>
        </div>
        <h3>欢迎回来，{{ authStore.username }}！</h3>
        <p>这是流式版，答案会逐字显示，体验更流畅～</p>
      </div>

      <div v-for="(msg, idx) in messages" :key="idx" class="message-wrapper">
        <div class="message" :class="[msg.role]">
          <div class="avatar">
            <svg v-if="msg.role === 'user'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <circle cx="12" cy="8" r="3.5" />
              <path d="M5 20c0-3.3 3.1-6 7-6s7 2.7 7 6" />
            </svg>
            <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <rect x="4" y="7" width="16" height="12" rx="3" />
              <path d="M12 7V4M9 13h.01M15 13h.01M9 16.5h6" />
            </svg>
          </div>
          <div class="message-bubble" v-html="renderContent(msg.content)"></div>
        </div>
      </div>

      <div v-if="loading" class="message assistant loading">
        <div class="avatar">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <rect x="4" y="7" width="16" height="12" rx="3" />
            <path d="M12 7V4M9 13h.01M15 13h.01M9 16.5h6" />
          </svg>
        </div>
        <div class="message-bubble">
          <span class="loading-dots">正在接收</span>
          <button class="stop-btn" @click="stopGenerating">
            <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true" style="width:9px;height:9px;vertical-align:middle;margin-right:4px">
              <rect x="6" y="6" width="12" height="12" rx="1.5" />
            </svg>停止
          </button>
        </div>
      </div>
    </div>

    <div class="chat-input-area">
      <div v-if="messages.length === 0" class="suggestions">
        <button class="suggestion-chip" @click="useSuggestion('介绍一下前进型蒸汽机车')">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M4 17h16M6 17V9a3 3 0 0 1 3-3h5l3 4v7M9 6V4M14 9h4" />
            <circle cx="8" cy="20" r="1.4" /><circle cx="16" cy="20" r="1.4" />
          </svg>机车知识
        </button>
        <button class="suggestion-chip" @click="useSuggestion('查询 Z227 车次信息')">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <rect x="5" y="3" width="14" height="13" rx="3" /><path d="M5 9h14M8 16l-2 4M16 16l2 4M4 20h16" />
          </svg>查车次
        </button>
        <button class="suggestion-chip" @click="useSuggestion('北京到合肥有哪些车次？')">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <circle cx="11" cy="11" r="6" /><path d="M20 20l-4.2-4.2" />
          </svg>路线推荐
        </button>
        <button class="suggestion-chip" @click="useSuggestion('生成 T35 次列车的运行路线地图')">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M3 6.5 9 4l6 2.5L21 4v13.5L15 20l-6-2.5L3 20z" /><path d="M9 4v13.5M15 6.5V20" />
          </svg>路线地图
        </button>
      </div>
      <div class="input-container">
        <textarea
          v-model="inputMessage"
          @keyup.enter.exact="sendMessage"
          @keyup.enter.shift.exact="handleShiftEnter"
          placeholder="输入你的铁路相关问题..."
          :disabled="loading"
          class="message-input"
          rows="1"
          ref="inputRef"
        ></textarea>
        <button @click="sendMessage" class="send-btn" :disabled="loading || !inputMessage.trim()">
          <svg class="send-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M4 12h15M13 6l6 6-6 6" />
          </svg>
        </button>
      </div>
      <div class="input-hint">
        <span>按 Enter 发送，Shift+Enter 换行</span>
      </div>
    </div>
    </div>

    <!-- 浮动错误提示：会话操作失败时给出可见反馈（3 秒自动消失） -->
    <transition name="toast">
      <div v-if="toastMessage" class="toast">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <circle cx="12" cy="12" r="9" /><path d="M12 7.5v5M12 16h.01" />
        </svg>{{ toastMessage }}
      </div>
    </transition>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, nextTick, watch, onBeforeUnmount } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { marked } from 'marked'
import hljs from 'highlight.js'
import 'highlight.js/styles/github-dark.css'
import { useRouter } from 'vue-router'
import HistorySidebar from '@/components/HistorySidebar.vue'
import type { SessionGroup } from '@/components/HistorySidebar.vue'
import api from '@/services/api'
marked.setOptions({ breaks: true, gfm: true })

// 高亮代码块（marked v17 的 renderer.code 接收对象参数）
const renderer = new marked.Renderer()
renderer.code = ({ text, lang }) => {
  const language = lang || 'text'
  const valid = hljs.getLanguage(language) ? language : 'text'
  const highlighted = hljs.highlight(text, { language: valid }).value
  return `<pre><code class="hljs language-${valid}">${highlighted}</code></pre>`
}
marked.setOptions({ renderer })

/** 地图 URL 正则：/maps/xxx.html */
const MAP_URL_RE = /\/maps\/[A-Za-z0-9_-]+\.html/

/**
 * 渲染 markdown 内容，并将地图 URL 转为内嵌 iframe 卡片
 */
function renderContent(raw: string): string {
  // 先把地图 URL 替换为占位符，避免 markdown 干扰
  const mapUrls: string[] = []
  const safe = raw.replace(MAP_URL_RE, (url) => {
    mapUrls.push(url)
    return `__MAP_CARD_${mapUrls.length - 1}__`
  })
  let html = marked(safe) as string
  // 还原地图卡片
  html = html.replace(/__MAP_CARD_(\d+)__/g, (_, idx: string) => {
    const url = mapUrls[Number(idx)]
    return url ? renderMapCard(url) : ''
  })
  return html
}

/** 生成地图内嵌卡片 HTML */
function renderMapCard(url: string): string {
  return `
  <div class="map-card">
    <div class="map-card-header">交互式路线地图</div>
    <iframe src="${url}" class="map-frame" loading="lazy" title="路线地图"></iframe>
    <a class="map-card-link" href="${url}" target="_blank" rel="noopener">在新窗口打开 ↗</a>
  </div>`
}

const authStore = useAuthStore()
const router = useRouter()
const messages = ref<Array<{ role: string; content: string }>>([])
const inputMessage = ref('')
const loading = ref(false)
const messageListRef = ref<HTMLElement | null>(null)
const inputRef = ref<HTMLTextAreaElement | null>(null)
// 每个页面加载生成唯一 session_id，用于隔离不同会话
const sessionId = ref('')
// 用于中断流式请求
let abortController: AbortController | null = null

// 侧边栏状态
const sidebarCollapsed = ref(false)
const loadingSessions = ref(false)
const sessionGroups = ref<SessionGroup[]>([])
// 浮动错误提示（3 秒自动消失）
const toastMessage = ref('')
const activeThreadId = ref('')

// ── 侧边栏宽度拖拽 ──────────────────────────────
const SIDEBAR_MIN = 220
const SIDEBAR_MAX = 520
const SIDEBAR_DEFAULT = 280
const SIDEBAR_STORAGE_KEY = 'sidebar-width'

/** 从 localStorage 恢复宽度，非法值回退默认 */
function loadSidebarWidth(): number {
  const raw = localStorage.getItem(SIDEBAR_STORAGE_KEY)
  const n = raw ? Number.parseInt(raw, 10) : NaN
  if (Number.isFinite(n)) {
    return Math.min(SIDEBAR_MAX, Math.max(SIDEBAR_MIN, n))
  }
  return SIDEBAR_DEFAULT
}

const sidebarWidth = ref(loadSidebarWidth())
const isResizing = ref(false)

/** 拖拽分隔条：更新宽度并持久化 */
function startResize(e: MouseEvent) {
  if (sidebarCollapsed.value) return
  e.preventDefault()
  isResizing.value = true
  const startX = e.clientX
  const startWidth = sidebarWidth.value

  function onMove(ev: MouseEvent) {
    const next = startWidth + (ev.clientX - startX)
    sidebarWidth.value = Math.min(SIDEBAR_MAX, Math.max(SIDEBAR_MIN, next))
  }

  function onUp() {
    isResizing.value = false
    localStorage.setItem(SIDEBAR_STORAGE_KEY, String(sidebarWidth.value))
    document.removeEventListener('mousemove', onMove)
    document.removeEventListener('mouseup', onUp)
    document.body.style.removeProperty('cursor')
    document.body.style.removeProperty('user-select')
  }

  // 拖拽期间锁住光标与文本选择，避免划选内容
  document.body.style.cursor = 'col-resize'
  document.body.style.userSelect = 'none'
  document.addEventListener('mousemove', onMove)
  document.addEventListener('mouseup', onUp)
}

/** 键盘调整（左右方向键 ±16px） */
function onResizeKeydown(e: KeyboardEvent) {
  if (sidebarCollapsed.value) return
  let delta = 0
  if (e.key === 'ArrowLeft') delta = -16
  else if (e.key === 'ArrowRight') delta = 16
  else return
  e.preventDefault()
  sidebarWidth.value = Math.min(
    SIDEBAR_MAX,
    Math.max(SIDEBAR_MIN, sidebarWidth.value + delta),
  )
  localStorage.setItem(SIDEBAR_STORAGE_KEY, String(sidebarWidth.value))
}

/** 双击分隔条恢复默认宽度 */
function resetSidebarWidth() {
  sidebarWidth.value = SIDEBAR_DEFAULT
  localStorage.setItem(SIDEBAR_STORAGE_KEY, String(SIDEBAR_DEFAULT))
}

/** 点击快捷指令：填入输入框并发送 */
function useSuggestion(text: string) {
  if (loading.value) return
  inputMessage.value = text
  sendMessage()
}

/** 停止流式生成 */
function stopGenerating() {
  if (abortController) {
    abortController.abort()
  }
}

// 从 thread_id 中提取 session_id: user_{id}_{session_id}
function extractSessionId(threadId: string): string {
  const parts = threadId.split('_')
  return parts.slice(2).join('_')
}

/**
 * 统一的错误提示：闪一条 toast，而不是只 console.error
 * （此前失败只打日志，用户看到界面没反应，会误以为操作成功了）
 */
let toastTimer: ReturnType<typeof setTimeout> | null = null
function showToast(message: string) {
  toastMessage.value = message
  if (toastTimer) clearTimeout(toastTimer)
  toastTimer = setTimeout(() => {
    toastMessage.value = ''
  }, 3000)
}

/** 从 axios 错误中提取可读文案 */
function extractErrorMessage(e: unknown, fallback: string): string {
  const detail = (e as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (e instanceof Error && e.message) return e.message
  return fallback
}

async function fetchSessions() {
  loadingSessions.value = true
  try {
    // axios 拦截器自动注入 token；非 2xx 会抛异常，401 由响应拦截器统一处理
    const { data } = await api.get('/chat/sessions')
    sessionGroups.value = data.groups || []
  } catch (e) {
    console.error('获取历史会话失败', e)
    showToast(extractErrorMessage(e, '获取历史会话失败'))
  } finally {
    loadingSessions.value = false
  }
}

async function loadSession(threadId: string) {
  activeThreadId.value = threadId
  try {
    const { data } = await api.get(`/chat/sessions/${encodeURIComponent(threadId)}`)
    messages.value = data.messages || []
    // 切换到该会话的 session_id，后续发送消息会复用原会话
    sessionId.value = extractSessionId(threadId)
    await nextTick()
    scrollToBottom()
  } catch (e) {
    console.error('加载会话失败', e)
    showToast(extractErrorMessage(e, '加载会话失败'))
  }
}

/** 重命名会话（行内编辑确认后调用） */
async function renameSession(threadId: string, newTitle: string) {
  try {
    const { data } = await api.put(`/chat/sessions/${encodeURIComponent(threadId)}`, {
      title: newTitle,
    })
    if (data.ok) {
      fetchSessions()
    } else {
      showToast(data.error || '重命名失败')
    }
  } catch (e) {
    console.error('重命名会话失败', e)
    showToast(extractErrorMessage(e, '重命名会话失败'))
  }
}

/** 删除会话 */
async function deleteSession(threadId: string) {
  if (!window.confirm('确定删除这个会话吗？')) return
  try {
    const { data } = await api.delete(`/chat/sessions/${encodeURIComponent(threadId)}`)
    if (data.ok) {
      // 如果删除的是当前激活会话，清空消息
      if (threadId === activeThreadId.value) {
        activeThreadId.value = ''
        sessionId.value = crypto.randomUUID()
        messages.value = []
      }
      fetchSessions()
    } else {
      showToast(data.error || '删除失败')
    }
  } catch (e) {
    console.error('删除会话失败', e)
    showToast(extractErrorMessage(e, '删除会话失败'))
  }
}

function startNewChat() {
  sessionId.value = crypto.randomUUID()
  activeThreadId.value = ''
  messages.value = []
  // 刷新侧边栏会话列表
  fetchSessions()
}

const adjustTextareaHeight = () => {
  if (inputRef.value) {
    inputRef.value.style.height = 'auto'
    inputRef.value.style.height = `${Math.min(inputRef.value.scrollHeight, 200)}px`
  }
}
watch(inputMessage, () => nextTick(adjustTextareaHeight))

const scrollToBottom = () => {
  nextTick(() => {
    if (messageListRef.value) {
      messageListRef.value.scrollTop = messageListRef.value.scrollHeight
    }
  })
}

const handleShiftEnter = () => {
  inputMessage.value += '\n'
  nextTick(() => {
    adjustTextareaHeight()
    inputRef.value?.focus()
  })
}

async function sendMessage() {
  const trimmedMessage = inputMessage.value.trim()
  if (!trimmedMessage || loading.value) return

  messages.value.push({ role: 'user', content: trimmedMessage })
  inputMessage.value = ''
  adjustTextareaHeight()
  loading.value = true
  scrollToBottom()

  // 创建新的 AbortController 用于停止生成
  abortController = new AbortController()
  const signal = abortController.signal

  try {
    // ⚠️ 这里必须用原生 fetch 而非 axios：浏览器里 axios 基于 XHR，
    // 拿不到 ReadableStream，无法用 response.body.getReader() 逐块读 SSE。
    // 因此需要手动带 Authorization 头（不走 axios 拦截器）。
    const response = await fetch('/chat/stream', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${authStore.token || ''}`,
      },
      body: JSON.stringify({ message: trimmedMessage, session_id: sessionId.value }),
      signal,
    })

    if (!response.ok) throw new Error(`请求失败：${response.status}`)
    if (!response.body) throw new Error('响应体为空')

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let assistantMessage = ''
    // 跨 read 的事件缓冲区：网络分包可能把一个 SSE 事件切在两个包里，
    // 不完整的尾巴留在这里，与下一次 read 的数据拼接后再解析
    let buffer = ''

    messages.value.push({ role: 'assistant', content: '' })
    const lastIndex = messages.value.length - 1

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n\n')
      // 最后一段可能是被切断的半个事件（或空串）→ 留在缓冲区等下次拼接
      buffer = lines.pop() ?? ''
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const data = line.slice(6).trim()
          if (data === '[DONE]') continue
          try {
            const parsed = JSON.parse(data)
            if (parsed.content) {
              assistantMessage += parsed.content
              const msg = messages.value[lastIndex]
              if (msg) msg.content = assistantMessage
              scrollToBottom()
            } else if (parsed.error) {
              // 后端推送的错误事件（超时等），追加到当前助手消息后
              assistantMessage += `\n\n⚠️ 服务异常：${parsed.error}`
              const msg = messages.value[lastIndex]
              if (msg) msg.content = assistantMessage
              scrollToBottom()
              // 出错后放弃当前会话，后续发消息走新会话
              sessionId.value = crypto.randomUUID()
              activeThreadId.value = ''
            }
          } catch (e) {
            console.error('解析错误', e)
          }
        }
      }
    }
  } catch (error) {
    // 用户主动停止 → 不视为错误，保留已生成内容
    if (error instanceof DOMException && error.name === 'AbortError') {
      const msg = messages.value[messages.value.length - 1]
      if (msg && msg.role === 'assistant') {
        msg.content += '\n\n⏹️ (已停止生成)'
      }
      scrollToBottom()
      return
    }
    let errorMsg = '未知错误'
    if (error instanceof Error) errorMsg = error.message
    if (errorMsg.includes('401')) {
      messages.value.push({ role: 'assistant', content: '⏰ 登录已过期，正在跳转到登录页...' })
      await new Promise(r => setTimeout(r, 1500))
      authStore.logout()
      router.push('/login')
      return
    }
    messages.value.push({ role: 'assistant', content: `⚠️ 请求失败：${errorMsg}` })
    // 连接异常（超时等）→ 放弃当前会话，下次发消息从新会话开始
    sessionId.value = crypto.randomUUID()
    activeThreadId.value = ''
  } finally {
    loading.value = false
    abortController = null
    scrollToBottom()
    // 消息发送完成后刷新会话列表
    fetchSessions()
  }
}

function logout() {
  authStore.logout()
  router.push('/login')
}

onMounted(() => {
  if (!authStore.token) {
    router.push('/login')
    return
  }
  sessionId.value = crypto.randomUUID()
  fetchSessions()
  adjustTextareaHeight()
  scrollToBottom()
})

onBeforeUnmount(() => {
  // 组件卸载时中断未完成的流式请求
  if (abortController) {
    abortController.abort()
  }
})
</script>

<style scoped>
.app-layout {
  height: 100vh;
  display: flex;
  flex-direction: row;
  background: var(--ink-900);
  font-family: var(--font-body);
  overflow: hidden;
}

.main-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

/* ── 侧边栏拖拽分隔条 ─────────────────────────── */
.resize-handle {
  flex: 0 0 auto;
  width: 5px;
  cursor: col-resize;
  background: transparent;
  position: relative;
  z-index: 15;
  /* 扩大命中区域，但视觉保持细线 */
  margin: 0 -2px;
  transition: background var(--dur-fast) var(--ease);
}

/* 视觉细线用伪元素，避免撑宽布局 */
.resize-handle::before {
  content: '';
  position: absolute;
  inset: 0 2px;
  background: var(--border);
  transition: background var(--dur-fast) var(--ease);
}

.resize-handle:hover::before,
.resize-handle.dragging::before {
  background: var(--accent);
}

.resize-handle.dragging::before {
  inset: 0 1px;
}

.resize-handle:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: -1px;
}

@media (max-width: 768px) {
  /* 窄屏下不提供拖拽，避免误触 */
  .resize-handle {
    display: none;
  }
}

/* ── 顶栏 ─────────────────────────────────────── */
.chat-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--sp-3) var(--sp-6);
  background: var(--ink-800);
  border-bottom: 1px solid var(--border);
  color: var(--text-100);
  position: relative;
  z-index: 10;
}

.header-left {
  display: flex;
  align-items: center;
  gap: var(--sp-3);
}

.logo {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  border-radius: var(--r-sm);
  background: var(--accent);
  color: var(--ink-900);
}

.logo svg {
  width: 20px;
  height: 20px;
}

.header-text h2 {
  margin: 0;
  font-weight: 600;
  font-size: var(--fs-lg);
  letter-spacing: -0.01em;
  text-wrap: balance;
}

.online-status {
  font-size: var(--fs-xs);
  color: var(--text-300);
  display: flex;
  align-items: center;
  gap: var(--sp-1);
}

.online-status::before {
  content: '';
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--ok);
}

.logout-btn {
  padding: var(--sp-2) var(--sp-4);
  border-radius: var(--r-sm);
  background: transparent;
  color: var(--text-200);
  font-size: var(--fs-sm);
  cursor: pointer;
  transition:
    background var(--dur-fast) var(--ease),
    color var(--dur-fast) var(--ease);
  border: 1px solid var(--border);
}

.logout-btn:hover {
  background: var(--ink-700);
  color: var(--text-100);
  border-color: var(--border-strong);
}

.logout-btn:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}

.logout-btn:active {
  background: var(--ink-600);
}

.header-right {
  display: flex;
  align-items: center;
  gap: var(--sp-2);
}

/* ── 消息区 ───────────────────────────────────── */
.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: var(--sp-6);
  display: flex;
  flex-direction: column;
  gap: var(--sp-5);
  background: var(--ink-900);
  position: relative;
}

.welcome-message {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  text-align: center;
  color: var(--text-200);
  padding: var(--sp-8);
}

.welcome-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 48px;
  height: 48px;
  border-radius: var(--r-md);
  background: var(--accent-wash);
  color: var(--accent);
  margin-bottom: var(--sp-4);
}

.welcome-icon svg {
  width: 26px;
  height: 26px;
}

.welcome-message h3 {
  font-size: var(--fs-xl);
  font-weight: 600;
  margin-bottom: var(--sp-2);
  color: var(--text-100);
}

.welcome-message p {
  max-width: 460px;
  margin-bottom: var(--sp-6);
  color: var(--text-300);
  font-size: var(--fs-base);
  line-height: 1.6;
}

.suggestions {
  display: flex;
  gap: var(--sp-2);
  flex-wrap: wrap;
  justify-content: center;
}

.suggest-btn {
  padding: var(--sp-2) var(--sp-4);
  border: 1px solid var(--border);
  border-radius: var(--r-sm);
  background: var(--ink-800);
  color: var(--text-200);
  font-size: var(--fs-sm);
  cursor: pointer;
  transition:
    border-color var(--dur-fast) var(--ease),
    color var(--dur-fast) var(--ease),
    background var(--dur-fast) var(--ease);
}

.suggest-btn:hover {
  border-color: var(--accent-line);
  color: var(--text-100);
  background: var(--ink-700);
}

.suggest-btn:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}

.suggest-btn:active {
  background: var(--ink-600);
}

/* ── 消息气泡 ─────────────────────────────────── */
.message-wrapper {
  width: 100%;
}

.message {
  display: flex;
  gap: var(--sp-3);
  animation: message-fade-in var(--dur-mid) var(--ease) forwards;
  opacity: 0;
  transform: translateY(6px);
}

@keyframes message-fade-in {
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.message.user {
  justify-content: flex-end;
}

.message.assistant {
  justify-content: flex-start;
}

.avatar {
  width: 30px;
  height: 30px;
  border-radius: var(--r-sm);
  background: var(--ink-700);
  color: var(--text-300);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.avatar svg {
  width: 16px;
  height: 16px;
}

.message.user .avatar {
  background: var(--accent-wash);
  color: var(--accent);
}

.message-bubble {
  max-width: 72%;
  padding: var(--sp-3) var(--sp-4);
  border-radius: var(--r-md);
  background: var(--ink-800);
  border: 1px solid var(--border);
  color: var(--text-100);
  line-height: 1.65;
  font-size: var(--fs-base);
  word-wrap: break-word;
  position: relative;
}

.message.user .message-bubble {
  background: var(--accent-wash);
  border-color: var(--accent-line);
  border-bottom-right-radius: 2px;
}

.message.assistant .message-bubble {
  background: var(--ink-800);
  border-bottom-left-radius: 2px;
}

.loading .message-bubble {
  background: transparent;
  border: 1px solid var(--border);
}

.loading-dots {
  color: var(--text-300);
  display: inline-block;
  font-size: var(--fs-sm);
}

.loading-dots::after {
  content: '';
  animation: dots 1.4s steps(4, end) infinite;
}

@keyframes dots {
  0% {
    content: '';
  }
  25% {
    content: '.';
  }
  50% {
    content: '..';
  }
  75% {
    content: '...';
  }
}

/* ── 输入区 ───────────────────────────────────── */
.chat-input-area {
  padding: var(--sp-4) var(--sp-6) var(--sp-5);
  background: var(--ink-800);
  border-top: 1px solid var(--border);
  position: relative;
  z-index: 10;
}

.suggestions + .input-container {
  margin-top: var(--sp-4);
}

.input-container {
  display: flex;
  gap: var(--sp-2);
  background: var(--ink-700);
  border-radius: var(--r-md);
  padding: var(--sp-1);
  border: 1px solid var(--border);
  transition: border-color var(--dur-fast) var(--ease);
}

.input-container:focus-within {
  border-color: var(--border-strong);
  outline: 2px solid var(--accent-line);
  outline-offset: 1px;
}

.message-input {
  flex: 1;
  padding: var(--sp-2) var(--sp-3);
  border: none;
  border-radius: var(--r-sm);
  background: transparent;
  color: var(--text-100);
  font-size: var(--fs-base);
  outline: none;
  resize: none;
  min-height: 38px;
  max-height: 200px;
  font-family: var(--font-body);
  line-height: 1.5;
}

.message-input::placeholder {
  color: var(--text-400);
}

.send-btn {
  width: 38px;
  height: 38px;
  border-radius: var(--r-sm);
  border: none;
  background: var(--accent);
  color: var(--ink-900);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition:
    background var(--dur-fast) var(--ease),
    opacity var(--dur-fast) var(--ease);
  flex-shrink: 0;
}

.send-btn svg {
  width: 17px;
  height: 17px;
}

.send-btn:hover:not(:disabled) {
  background: var(--accent-hover);
}

.send-btn:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}

.send-btn:active:not(:disabled) {
  background: var(--accent-dim);
}

.send-btn:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}

.input-hint {
  margin-top: var(--sp-2);
  text-align: center;
  font-size: var(--fs-xs);
  color: var(--text-400);
}

/* ── 快捷指令 chips ───────────────────────────── */
.suggestion-chip {
  display: inline-flex;
  align-items: center;
  gap: var(--sp-2);
  padding: var(--sp-2) var(--sp-4);
  border: 1px solid var(--border);
  border-radius: var(--r-sm);
  background: var(--ink-800);
  color: var(--text-200);
  font-size: var(--fs-sm);
  cursor: pointer;
  transition:
    border-color var(--dur-fast) var(--ease),
    background var(--dur-fast) var(--ease),
    color var(--dur-fast) var(--ease);
  white-space: nowrap;
}

.suggestion-chip svg {
  width: 14px;
  height: 14px;
  color: var(--accent);
}

.suggestion-chip:hover {
  border-color: var(--accent-line);
  background: var(--ink-700);
  color: var(--text-100);
}

.suggestion-chip:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}

.suggestion-chip:active {
  background: var(--ink-600);
}

/* ── 停止生成 ─────────────────────────────────── */
.stop-btn {
  margin-left: var(--sp-3);
  padding: var(--sp-1) var(--sp-3);
  border: 1px solid var(--danger);
  border-radius: var(--r-sm);
  background: transparent;
  color: var(--danger);
  font-size: var(--fs-xs);
  cursor: pointer;
  transition:
    background var(--dur-fast) var(--ease),
    color var(--dur-fast) var(--ease);
}

.stop-btn:hover {
  background: var(--danger-wash);
}

.stop-btn:focus-visible {
  outline: 2px solid var(--danger);
  outline-offset: 2px;
}

/* ── 地图卡片 ─────────────────────────────────── */
.map-card {
  margin: var(--sp-2) 0;
  border: 1px solid var(--border);
  border-radius: var(--r-md);
  overflow: hidden;
  background: var(--ink-900);
}

.map-card-header {
  padding: var(--sp-2) var(--sp-3);
  font-size: var(--fs-xs);
  font-weight: 600;
  color: var(--text-200);
  background: var(--ink-700);
  border-bottom: 1px solid var(--border);
}

.map-frame {
  width: 100%;
  height: 340px;
  border: none;
  display: block;
}

.map-card-link {
  display: block;
  padding: var(--sp-2) var(--sp-3);
  font-size: var(--fs-xs);
  color: var(--accent);
  text-decoration: none;
  background: var(--ink-800);
  text-align: right;
  transition:
    background var(--dur-fast) var(--ease),
    color var(--dur-fast) var(--ease);
}

.map-card-link:hover {
  color: var(--accent-hover);
  background: var(--ink-700);
}

.map-card-link:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: -2px;
}

/* ── Markdown 代码块 ──────────────────────────── */
.message-bubble pre {
  background: var(--ink-900);
  border: 1px solid var(--border);
  border-radius: var(--r-sm);
  padding: var(--sp-3);
  overflow-x: auto;
  margin: var(--sp-2) 0;
}

.message-bubble pre code {
  font-family: var(--font-mono);
  font-size: var(--fs-sm);
  color: var(--text-200);
}

.message-bubble code {
  font-family: var(--font-mono);
  background: var(--ink-900);
  padding: 0 var(--sp-1);
  border-radius: 4px;
  font-size: var(--fs-sm);
  color: var(--text-200);
}

.message-bubble a {
  color: var(--accent);
  text-decoration: none;
  border-bottom: 1px solid var(--accent-line);
}

.message-bubble a:hover {
  color: var(--accent-hover);
}

/* ── 浮动提示 ─────────────────────────────────── */
.toast {
  position: fixed;
  top: var(--sp-6);
  left: 50%;
  transform: translateX(-50%);
  z-index: 1000;
  display: flex;
  align-items: center;
  gap: var(--sp-2);
  padding: var(--sp-2) var(--sp-4);
  border-radius: var(--r-sm);
  background: var(--danger);
  color: var(--text-100);
  font-size: var(--fs-sm);
  box-shadow: 0 6px 20px var(--shadow-toast);
  pointer-events: none;
}

.toast svg {
  width: 15px;
  height: 15px;
  flex-shrink: 0;
}

.toast-enter-active,
.toast-leave-active {
  transition:
    opacity var(--dur-fast) var(--ease),
    transform var(--dur-fast) var(--ease);
}

.toast-enter-from,
.toast-leave-to {
  opacity: 0;
  transform: translateX(-50%) translateY(-8px);
}

/* ── 响应式 ───────────────────────────────────── */
@media (max-width: 768px) {
  .chat-header {
    padding: var(--sp-3) var(--sp-4);
  }

  .chat-messages {
    padding: var(--sp-4);
  }

  .chat-input-area {
    padding: var(--sp-3) var(--sp-4) var(--sp-4);
  }

  .message-bubble {
    max-width: 88%;
  }

  .welcome-message {
    padding: var(--sp-4);
  }

  .suggestions {
    flex-direction: column;
    width: 100%;
  }
}

@media (max-width: 480px) {
  .logout-text {
    display: none;
  }

  .header-text h2 {
    font-size: var(--fs-base);
  }

  .message-bubble {
    padding: var(--sp-3);
    font-size: var(--fs-sm);
  }
}

@media (prefers-reduced-motion: reduce) {
  .message {
    animation: none;
    opacity: 1;
    transform: none;
  }

  .loading-dots::after {
    animation: none;
    content: '…';
  }
}
</style>
