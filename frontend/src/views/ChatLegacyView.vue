<template>
  <div class="chat-page">
    <!-- 顶部导航 -->
    <header class="chat-header">
      <div class="header-left">
        <div class="logo">🚂</div>
        <div class="header-text">
          <h2>铁路历史专家</h2>
          <p class="online-status">已连接 · 响应迅速</p>
        </div>
      </div>
      <button
        class="logout-btn"
        @click="logout"
        :class="{ 'btn-hover': logoutHover }"
        @mouseenter="logoutHover = true"
        @mouseleave="logoutHover = false"
      >
        <span class="logout-icon">🚪</span>
        <span class="logout-text">退出</span>
      </button>
    </header>

    <!-- 消息区域 -->
    <div class="chat-messages" ref="messageListRef">
      <!-- 欢迎消息 -->
      <div v-if="messages.length === 0" class="welcome-message">
        <div class="welcome-icon">👋</div>
        <h3>欢迎回来，{{ authStore.username }}！</h3>
        <p>我是你的铁路历史专属助手，有任何问题都可以问我～</p>
        <div class="suggestions">
          <button class="suggest-btn" @click="sendSuggestion('中国第一条铁路是什么？')">
            中国第一条铁路是什么？
          </button>
          <button class="suggest-btn" @click="sendSuggestion('蒸汽机车的发展历史')">
            蒸汽机车的发展历史
          </button>
        </div>
      </div>

      <!-- 消息列表 -->
      <div v-for="(msg, idx) in messages" :key="idx" class="message-wrapper">
        <div class="message" :class="[msg.role]" :style="{ animationDelay: `${idx * 0.1}s` }">
          <div class="avatar">
            {{ msg.role === 'user' ? '👤' : '🤖' }}
          </div>
          <div class="message-bubble" v-html="marked(msg.content)"></div>
        </div>
      </div>

      <!-- 加载状态 -->
      <div v-if="loading" class="message assistant loading">
        <div class="avatar">🤖</div>
        <div class="message-bubble">
          <span class="loading-dots">正在思考</span>
        </div>
      </div>
    </div>

    <!-- 输入区域 -->
    <div class="chat-input-area">
      <div class="input-container" :class="{ 'input-focused': inputFocus }">
        <textarea
          v-model="inputMessage"
          @keyup.enter.exact="sendMessage"
          @keyup.enter.shift.exact="handleShiftEnter"
          @focus="inputFocus = true"
          @blur="inputFocus = false"
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
</template>

<script setup lang="ts">
import { ref, onMounted, nextTick, watch } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { marked } from 'marked'
import { useRouter } from 'vue-router'

// 配置marked
marked.setOptions({
  breaks: true,
  gfm: true,
})

const authStore = useAuthStore()
const router = useRouter()
const messages = ref<Array<{ role: string; content: string }>>([])
const inputMessage = ref('')
const loading = ref(false)
const messageListRef = ref<HTMLElement | null>(null)
const inputRef = ref<HTMLTextAreaElement | null>(null)
const inputFocus = ref(false)
const logoutHover = ref(false)

// 自动调整文本框高度
const adjustTextareaHeight = () => {
  // 修复：添加非空判断
  if (inputRef.value) {
    inputRef.value.style.height = 'auto'
    inputRef.value.style.height = `${Math.min(inputRef.value.scrollHeight, 200)}px`
  }
}

// 监听输入内容变化，自动调整高度
watch(inputMessage, () => {
  nextTick(adjustTextareaHeight)
})

// 滚动到底部
const scrollToBottom = () => {
  nextTick(() => {
    // 修复：添加非空判断
    if (messageListRef.value) {
      messageListRef.value.scrollTop = messageListRef.value.scrollHeight
    }
  })
}

// 发送建议问题
const sendSuggestion = (text: string) => {
  inputMessage.value = text
  sendMessage()
}

// 处理Shift+Enter换行
const handleShiftEnter = () => {
  inputMessage.value += '\n'
  nextTick(() => {
    adjustTextareaHeight()
    // 修复：使用可选链操作符
    inputRef.value?.focus()
  })
}

// 发送消息
async function sendMessage() {
  const trimmedMessage = inputMessage.value.trim()
  if (!trimmedMessage || loading.value) return

  // 添加用户消息
  messages.value.push({ role: 'user', content: trimmedMessage })
  inputMessage.value = ''
  loading.value = true

  // 重置文本框高度
  adjustTextareaHeight()
  scrollToBottom()

  try {
    const response = await fetch('http://localhost:8000/chat', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${authStore.token || ''}`,
      },
      body: JSON.stringify({ message: trimmedMessage }),
    })

    if (!response.ok) {
      throw new Error(`请求失败：${response.status} ${response.statusText}`)
    }

    const data = await response.json()
    const answer = data.answer

    // 模拟打字效果
    let displayText = ''
    const assistantMsgIndex =
      messages.value.push({
        role: 'assistant',
        content: '',
      }) - 1

    const typingSpeed = 15 // 打字速度（毫秒/字符）
    const answerArray = answer.split('')

    for (let i = 0; i < answerArray.length; i++) {
      displayText += answerArray[i]
      messages.value[assistantMsgIndex].content = displayText
      scrollToBottom()
      await new Promise((resolve) => setTimeout(resolve, typingSpeed))
    }
  } catch (error) {
    let errorMsg = '未知错误'
    if (error instanceof Error) {
      errorMsg = error.message
    } else if (error && typeof error === 'object' && 'message' in error) {
      errorMsg = String(error.message)
    }

    console.error('发送消息失败:', errorMsg)
    messages.value.push({
      role: 'assistant',
      content: `⚠️ 请求失败：${errorMsg}，请检查网络或稍后重试。`,
    })
  } finally {
    loading.value = false
    scrollToBottom()
  }
}

// 退出登录
function logout() {
  authStore.logout()
  router.push('/login') // 改用router跳转，更丝滑
}

// 初始化
onMounted(() => {
  if (!authStore.token) {
    router.push('/login')
    return
  }

  adjustTextareaHeight()
  scrollToBottom()

  // 监听滚动条，添加渐变效果
  // 修复：添加非空判断
  const messageList = messageListRef.value
  if (messageList) {
    messageList.addEventListener('scroll', () => {
      if (messageList.scrollTop > 50) {
        messageList.classList.add('scrolled')
      } else {
        messageList.classList.remove('scrolled')
      }
    })
  }
})
</script>

<style scoped>
/* 样式部分完全不变，此处省略（保持之前的样式代码） */
.chat-page {
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: transparent;
  font-family:
    'Inter',
    -apple-system,
    BlinkMacSystemFont,
    sans-serif;
  overflow: hidden;
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

.btn-hover {
  background: rgba(255, 255, 255, 0.15);
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
</style>
