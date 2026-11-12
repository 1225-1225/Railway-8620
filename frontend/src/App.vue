<template>
  <div id="app">
    <transition name="page-transition" mode="out-in">
      <router-view />
    </transition>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore, isTokenExpired } from '@/stores/auth'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()

let timer: ReturnType<typeof setInterval> | null = null

/** 每 30 秒检测一次令牌是否过期，过期则强制跳转登录 */
function checkTokenExpiry() {
  const token = authStore.token
  if (!token) return
  if (isTokenExpired(token)) {
    authStore.logout()
    if (route.path !== '/login') {
      router.push({ path: '/login', query: { redirect: route.fullPath } })
    }
  }
}

onMounted(() => {
  timer = setInterval(checkTokenExpiry, 30_000)
})

onUnmounted(() => {
  if (timer) {
    clearInterval(timer)
    timer = null
  }
})
</script>

<style>
/* 设计令牌：所有颜色/字体/间距的唯一来源，页面内不允许出现字面值 */
:root {
  /* —— 主色：深蓝灰（铁路信号蓝 + 石墨灰）—— */
  --ink-900: #0f1720; /* 最深：页面底 */
  --ink-800: #16202b; /* 面板 */
  --ink-700: #1e2a37; /* 卡片 */
  --ink-600: #2a3947; /* 分隔线、边框 */
  --ink-500: #3d4f61; /* 禁用态 */

  /* —— 正文与次要文字 —— */
  --text-100: #eef2f6; /* 主文字 */
  --text-200: #c3ced9; /* 次要文字 */
  --text-300: #8a9aab; /* 提示、说明 */
  --text-400: #667586; /* 极弱（时间戳、占位符），与主色同源调过 */

  /* —— 强调色：单一，铁路信号橙（道岔标志色）—— */
  --accent: #e8712c;
  --accent-hover: #f08342;
  --accent-dim: #b8561f;
  --accent-wash: rgba(232, 113, 44, 0.12);
  --accent-line: rgba(232, 113, 44, 0.38);

  /* —— 状态色 —— */
  --ok: #4a9d6b;
  --warn: #d9a441;
  --danger: #c9524a;
  --danger-wash: rgba(201, 82, 74, 0.12);

  /* —— 表面与描边 —— */
  --surface: var(--ink-800);
  --surface-raised: var(--ink-700);
  --border: var(--ink-600);
  --border-strong: #38495a;

  /* —— 字体：系统字体栈，不使用 Inter —— */
  --font-body:
    -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC',
    'Hiragino Sans GB', 'Microsoft YaHei', 'Source Han Sans SC', sans-serif;
  --font-mono: 'SF Mono', 'Cascadia Mono', Consolas, 'Courier New', monospace;

  /* —— 字号 —— */
  --fs-xs: 0.75rem;
  --fs-sm: 0.8125rem;
  --fs-base: 0.9375rem;
  --fs-lg: 1.0625rem;
  --fs-xl: 1.375rem;

  /* —— 间距（4px 基准）—— */
  --sp-1: 4px;
  --sp-2: 8px;
  --sp-3: 12px;
  --sp-4: 16px;
  --sp-5: 20px;
  --sp-6: 24px;
  --sp-8: 32px;
  --sp-10: 40px;

  /* —— 圆角 —— */
  --r-sm: 6px;
  --r-md: 10px;
  --r-lg: 14px;

  /* —— 动效 —— */
  --ease: cubic-bezier(0.4, 0, 0.2, 1);
  --dur-fast: 120ms;
  --dur-mid: 200ms;

  /* —— 阴影 —— */
  --shadow-toast: rgba(0, 0, 0, 0.4);
  --shadow-panel: rgba(0, 0, 0, 0.28);
}

* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

html,
body {
  height: 100%;
  font-family: var(--font-body);
  background: var(--ink-900);
  color: var(--text-100);
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  overflow-x: clip;
}

#app {
  min-height: 100vh;
  background: var(--ink-900);
}

/* 页面过渡：只用 opacity + transform，且尊重 reduced-motion */
.page-transition-enter-active {
  animation: page-fade-in var(--dur-mid) var(--ease) forwards;
}

.page-transition-leave-active {
  animation: page-fade-out var(--dur-fast) var(--ease) forwards;
}

@keyframes page-fade-in {
  from {
    opacity: 0;
    transform: translateY(6px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@keyframes page-fade-out {
  from {
    opacity: 1;
    transform: translateY(0);
  }
  to {
    opacity: 0;
    transform: translateY(-6px);
  }
}

@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
  }
}

/* 滚动条 */
::-webkit-scrollbar {
  width: 10px;
  height: 10px;
}

::-webkit-scrollbar-track {
  background: transparent;
}

::-webkit-scrollbar-thumb {
  background: var(--ink-600);
  border-radius: var(--r-sm);
  border: 2px solid var(--ink-900);
}

::-webkit-scrollbar-thumb:hover {
  background: var(--border-strong);
}
</style>
