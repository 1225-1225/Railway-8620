<template>
  <div class="app-layout">
    <HistorySidebar
      :collapsed="sidebarCollapsed"
      :loading="loadingSessions"
      :groups="sessionGroups"
      :active-thread-id="activeThreadId"
      @toggle="sidebarCollapsed = !sidebarCollapsed"
      @new-chat="startNewChat"
      @select-session="loadSession"
      @rename-session="renameSession"
      @delete-session="deleteSession"
    />
    <div class="main-area">
      <header class="chat-header">
        <div class="header-left">
          <div class="logo">🚂</div>
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
        <div class="welcome-icon">👋</div>
        <h3>欢迎回来，{{ authStore.username }}！</h3>
        <p>这是流式版，答案会逐字显示，体验更流畅～</p>
      </div>

      <div v-for="(msg, idx) in messages" :key="idx" class="message-wrapper">
        <div class="message" :class="[msg.role]">
          <div class="avatar">{{ msg.role === 'user' ? '👤' : '🤖' }}</div>
          <div class="message-bubble" v-html="renderContent(msg.content)"></div>
        </div>
      </div>

      <div v-if="loading" class="message assistant loading">
        <div class="avatar">🤖</div>
        <div class="message-bubble">
          <span class="loading-dots">正在接收</span>
          <button class="stop-btn" @click="stopGenerating">■ 停止</button>
        </div>
      </div>
    </div>

    <div class="chat-input-area">
      <div v-if="messages.length === 0" class="suggestions">
        <button class="suggestion-chip" @click="useSuggestion('介绍一下前进型蒸汽机车')">🚂 机车知识</button>
        <button class="suggestion-chip" @click="useSuggestion('查询 Z227 车次信息')">🚄 查车次</button>
        <button class="suggestion-chip" @click="useSuggestion('北京到合肥有哪些车次？')">🔍 路线推荐</button>
        <button class="suggestion-chip" @click="useSuggestion('生成 T35 次列车的运行路线地图')">🗺️ 路线地图</button>
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
          <span class="send-icon">✈️</span>
        </button>
      </div>
      <div class="input-hint">
        <span>按 Enter 发送，Shift+Enter 换行</span>
      </div>
    </div>
    </div>
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
const MAP_URL_RE = /\/maps\/[A-Za-z0-9_\-]+\.html/

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
    <div class="map-card-header">🗺️ 交互式路线地图</div>
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
const activeThreadId = ref('')

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

async function fetchSessions() {
  loadingSessions.value = true
  try {
    const res = await fetch('/chat/sessions', {
      headers: { Authorization: `Bearer ${authStore.token || ''}` },
    })
    if (!res.ok) return
    const data = await res.json()
    sessionGroups.value = data.groups || []
  } catch (e) {
    console.error('获取历史会话失败', e)
  } finally {
    loadingSessions.value = false
  }
}

async function loadSession(threadId: string) {
  activeThreadId.value = threadId
  try {
    const res = await fetch(`/chat/sessions/${encodeURIComponent(threadId)}`, {
      headers: { Authorization: `Bearer ${authStore.token || ''}` },
    })
    if (!res.ok) return
    const data = await res.json()
    messages.value = data.messages || []
    // 切换到该会话的 session_id，后续发送消息会复用原会话
    sessionId.value = extractSessionId(threadId)
    await nextTick()
    scrollToBottom()
  } catch (e) {
    console.error('加载会话失败', e)
  }
}

/** 重命名会话（行内编辑确认后调用） */
async function renameSession(threadId: string, newTitle: string) {
  try {
    const res = await fetch(`/chat/sessions/${encodeURIComponent(threadId)}`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${authStore.token || ''}`,
      },
      body: JSON.stringify({ title: newTitle }),
    })
    if (!res.ok) return
    const data = await res.json()
    if (data.ok) {
      fetchSessions()
    }
  } catch (e) {
    console.error('重命名会话失败', e)
  }
}

/** 删除会话 */
async function deleteSession(threadId: string) {
  if (!window.confirm('确定删除这个会话吗？')) return
  try {
    const res = await fetch(`/chat/sessions/${encodeURIComponent(threadId)}`, {
      method: 'DELETE',
      headers: { Authorization: `Bearer ${authStore.token || ''}` },
    })
    if (!res.ok) return
    const data = await res.json()
    if (data.ok) {
      // 如果删除的是当前激活会话，清空消息
      if (threadId === activeThreadId.value) {
        activeThreadId.value = ''
        sessionId.value = crypto.randomUUID()
        messages.value = []
      }
      fetchSessions()
    }
  } catch (e) {
    console.error('删除会话失败', e)
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

    messages.value.push({ role: 'assistant', content: '' })
    const lastIndex = messages.value.length - 1

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      const chunk = decoder.decode(value, { stream: true })
      const lines = chunk.split('\n\n')
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
/* 样式部分完全不变，此处省略（保持之前的样式代码） */
.app-layout {
  height: 100vh;
  display: flex;
  flex-direction: row;
  background: transparent;
  font-family:
    'Inter',
    -apple-system,
    BlinkMacSystemFont,
    sans-serif;
  overflow: hidden;
}

.main-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.chat-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem 2rem;
  background: rgba(255, 255, 255, 0.05);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
  color: white;
  position: relative;
  z-index: 10;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.logo {
  font-size: 1.8rem;
  animation: pulse 2s infinite alternate;
}

@keyframes pulse {
  from {
    transform: scale(1);
  }
  to {
    transform: scale(1.05);
  }
}

.header-text h2 {
  margin: 0;
  font-weight: 600;
  font-size: 1.3rem;
  text-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
}

.online-status {
  font-size: 0.8rem;
  color: rgba(255, 255, 255, 0.6);
  display: flex;
  align-items: center;
  gap: 0.3rem;
}

.online-status::before {
  content: '';
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #22c55e;
  animation: blink 2s infinite;
}

@keyframes blink {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.5;
  }
}

.logout-btn {
  padding: 0.6rem 1.2rem;
  border: none;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.08);
  backdrop-filter: blur(4px);
  color: white;
  font-size: 0.9rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.3s ease;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  border: 1px solid rgba(255, 255, 255, 0.1);
}

.logout-btn:hover {
  background: rgba(255, 255, 255, 0.15);
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
}

.header-right {
  display: flex;
  align-items: center;
  gap: 0.6rem;
}

.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 1.5rem 2rem;
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
  background: rgba(0, 0, 0, 0.05);
  position: relative;
  transition: all 0.3s ease;
}

.chat-messages.scrolled {
  background: rgba(0, 0, 0, 0.08);
}

.chat-messages::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 40px;
  background: linear-gradient(to bottom, rgba(90, 103, 216, 0.1), transparent);
  pointer-events: none;
  z-index: 1;
}

.welcome-message {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  text-align: center;
  color: rgba(255, 255, 255, 0.8);
  padding: 2rem;
}

.welcome-icon {
  font-size: 3rem;
  margin-bottom: 1rem;
  animation: bounce 2s infinite alternate;
}

.welcome-message h3 {
  font-size: 1.5rem;
  margin-bottom: 0.5rem;
  color: white;
}

.welcome-message p {
  max-width: 500px;
  margin-bottom: 2rem;
  color: rgba(255, 255, 255, 0.7);
}

.suggestions {
  display: flex;
  gap: 1rem;
  flex-wrap: wrap;
  justify-content: center;
}

.suggest-btn {
  padding: 0.8rem 1.2rem;
  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.08);
  color: white;
  font-size: 0.9rem;
  cursor: pointer;
  transition: all 0.3s ease;
}

.suggest-btn:hover {
  background: rgba(255, 255, 255, 0.15);
  transform: translateY(-2px);
}

.message-wrapper {
  width: 100%;
}

.message {
  display: flex;
  gap: 1rem;
  animation: message-fade-in 0.5s ease forwards;
  opacity: 0;
  transform: translateY(10px);
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
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.1);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  font-size: 1.2rem;
}

.message.user .avatar {
  background: rgba(90, 103, 216, 0.3);
}

.message-bubble {
  max-width: 70%;
  padding: 1rem 1.2rem;
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.1);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
  border: 1px solid rgba(255, 255, 255, 0.15);
  color: white;
  line-height: 1.6;
  word-wrap: break-word;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
  position: relative;
}

.message.user .message-bubble {
  background: linear-gradient(135deg, rgba(90, 103, 216, 0.3), rgba(139, 92, 246, 0.3));
  border-color: rgba(255, 255, 255, 0.2);
  border-bottom-right-radius: 4px;
}

.message.assistant .message-bubble {
  background: rgba(255, 255, 255, 0.08);
  border-bottom-left-radius: 4px;
}

.loading .message-bubble {
  background: transparent;
  border: none;
  box-shadow: none;
}

.loading-dots {
  color: rgba(255, 255, 255, 0.7);
  display: inline-block;
  position: relative;
}

.loading-dots::after {
  content: '';
  animation: dots 1.5s infinite;
}

@keyframes dots {
  0% {
    content: '.';
  }
  33% {
    content: '..';
  }
  66% {
    content: '...';
  }
  100% {
    content: '.';
  }
}

.chat-input-area {
  padding: 1rem 2rem 1.5rem;
  background: rgba(255, 255, 255, 0.05);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border-top: 1px solid rgba(255, 255, 255, 0.1);
  position: relative;
  z-index: 10;
}

.input-container {
  display: flex;
  gap: 0.8rem;
  background: rgba(255, 255, 255, 0.08);
  border-radius: 20px;
  padding: 0.5rem;
  border: 1px solid rgba(255, 255, 255, 0.1);
  transition: all 0.3s ease;
}

.input-focused {
  border-color: rgba(255, 255, 255, 0.3);
  background: rgba(255, 255, 255, 0.1);
  box-shadow: 0 0 0 3px rgba(255, 255, 255, 0.05);
}

.message-input {
  flex: 1;
  padding: 0.8rem 1rem;
  border: none;
  border-radius: 16px;
  background: transparent;
  color: white;
  font-size: 1rem;
  outline: none;
  resize: none;
  min-height: 44px;
  max-height: 200px;
  font-family: inherit;
}

.message-input::placeholder {
  color: rgba(255, 255, 255, 0.4);
}

.send-btn {
  width: 44px;
  height: 44px;
  border-radius: 50%;
  border: none;
  background: linear-gradient(135deg, #5a67d8, #8b5cf6);
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.3s ease;
  flex-shrink: 0;
}

.send-btn:hover:not(:disabled) {
  transform: scale(1.05);
  box-shadow: 0 4px 12px rgba(139, 92, 246, 0.3);
}

.send-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
  transform: none;
}

.input-hint {
  margin-top: 0.8rem;
  text-align: center;
  font-size: 0.75rem;
  color: rgba(255, 255, 255, 0.4);
}

@media (max-width: 768px) {
  .chat-header {
    padding: 1rem;
  }

  .chat-messages {
    padding: 1rem;
  }

  .chat-input-area {
    padding: 1rem;
  }

  .message-bubble {
    max-width: 85%;
  }

  .welcome-message {
    padding: 1rem;
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
    font-size: 1.1rem;
  }

  .message-bubble {
    padding: 0.8rem;
    font-size: 0.95rem;
  }

}

/* ===== 快捷指令 Chips ===== */
.suggestion-chip {
  padding: 0.55rem 1.1rem;
  border: 1px solid rgba(255, 255, 255, 0.18);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.07);
  color: rgba(255, 255, 255, 0.85);
  font-size: 0.85rem;
  cursor: pointer;
  transition: all 0.25s ease;
  white-space: nowrap;
}

.suggestion-chip:hover {
  background: rgba(90, 103, 216, 0.25);
  border-color: rgba(90, 103, 216, 0.5);
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(90, 103, 216, 0.2);
}

/* ===== 停止生成按钮 ===== */
.stop-btn {
  margin-left: 0.8rem;
  padding: 0.3rem 0.8rem;
  border: 1px solid rgba(255, 100, 100, 0.4);
  border-radius: 8px;
  background: rgba(255, 100, 100, 0.15);
  color: rgba(255, 150, 150, 1);
  font-size: 0.75rem;
  cursor: pointer;
  transition: all 0.2s;
}

.stop-btn:hover {
  background: rgba(255, 100, 100, 0.3);
  border-color: rgba(255, 100, 100, 0.7);
}

/* ===== 地图卡片（内嵌 iframe） ===== */
.map-card {
  margin: 0.5rem 0;
  border: 1px solid rgba(255, 255, 255, 0.15);
  border-radius: 12px;
  overflow: hidden;
  background: rgba(0, 0, 0, 0.2);
}

.map-card-header {
  padding: 0.5rem 0.9rem;
  font-size: 0.8rem;
  font-weight: 600;
  color: rgba(255, 255, 255, 0.8);
  background: rgba(90, 103, 216, 0.2);
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
}

.map-frame {
  width: 100%;
  height: 340px;
  border: none;
  display: block;
}

.map-card-link {
  display: block;
  padding: 0.4rem 0.9rem;
  font-size: 0.75rem;
  color: rgba(139, 180, 255, 0.9);
  text-decoration: none;
  background: rgba(255, 255, 255, 0.05);
  text-align: right;
  transition: all 0.2s;
}

.map-card-link:hover {
  color: white;
  background: rgba(255, 255, 255, 0.1);
}

/* ===== Markdown 代码块高亮 ===== */
.message-bubble pre {
  background: rgba(0, 0, 0, 0.4);
  border-radius: 8px;
  padding: 0.8rem 1rem;
  overflow-x: auto;
  margin: 0.5rem 0;
}

.message-bubble pre code {
  font-family: 'Fira Code', 'Consolas', monospace;
  font-size: 0.85rem;
  color: #e2e8f0;
}

.message-bubble code {
  font-family: 'Fira Code', 'Consolas', monospace;
  background: rgba(0, 0, 0, 0.3);
  padding: 0.1rem 0.35rem;
  border-radius: 4px;
  font-size: 0.85rem;
}

</style>
