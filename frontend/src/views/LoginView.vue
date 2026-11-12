<template>
  <div class="login-page">
    <!-- 修复ESLint报错：transition内添加v-if + 正确的视图切换逻辑 -->
    <transition name="page-transition" mode="out-in">
      <div v-if="showLogin" key="login-form" class="login-container">
        <div class="login-card">
          <div class="card-header">
            <div class="logo">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                <rect x="5" y="3" width="14" height="13" rx="3" />
                <path d="M5 9h14" />
                <circle cx="9" cy="12.5" r="1" fill="currentColor" stroke="none" />
                <circle cx="15" cy="12.5" r="1" fill="currentColor" stroke="none" />
                <path d="M8 16l-2 4M16 16l2 4M4 20h16" />
              </svg>
            </div>
            <h2>铁路历史专家</h2>
            <p class="subtitle">专注于解答铁路相关的一切问题</p>
          </div>

          <form @submit.prevent="handleSubmit" class="login-form">
            <div class="form-group">
              <label class="input-label">
                <span class="label-text">用户名</span>
                <input
                  v-model="form.username"
                  type="text"
                  required
                  class="form-input"
                  placeholder="请输入用户名"
                  :class="{ 'input-focus': usernameFocus }"
                  @focus="usernameFocus = true"
                  @blur="usernameFocus = false"
                />
              </label>
            </div>

            <div class="form-group">
              <label class="input-label">
                <span class="label-text">密码</span>
                <input
                  v-model="form.password"
                  type="password"
                  required
                  class="form-input"
                  placeholder="请输入密码"
                  :class="{ 'input-focus': passwordFocus }"
                  @focus="passwordFocus = true"
                  @blur="passwordFocus = false"
                />
              </label>
            </div>

            <div v-if="error" class="error-message" :class="{ 'error-shake': errorShake }">
              {{ error }}
            </div>

            <button type="submit" class="submit-btn" :disabled="loading">
              <span v-if="loading" class="loading-spinner"></span>
              <span class="btn-text">{{ loading ? '登录中...' : '登录' }}</span>
            </button>

            <p class="register-link">
              没有账号？<router-link to="/register" class="link">注册</router-link>
            </p>
          </form>
        </div>
      </div>
    </transition>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const authStore = useAuthStore()
const router = useRouter()
const route = useRoute()

// 修复ESLint：添加transition所需的显式切换变量
const showLogin = ref(true)

// 表单状态
const form = ref({ username: '', password: '' })
const error = ref('')
const loading = ref(false)
const cardHover = ref(false)
const usernameFocus = ref(false)
const passwordFocus = ref(false)
const errorShake = ref(false)

async function handleSubmit() {
  error.value = ''
  loading.value = true

  try {
    await authStore.login(form.value)
    // 如果有重定向参数，跳回原页面；否则去聊天页
    const redirect = route.query.redirect as string | undefined
    router.push(redirect || '/chat')
  } catch (err: unknown) {
    // 错误处理
    errorShake.value = true
    setTimeout(() => (errorShake.value = false), 500)

    if (err && typeof err === 'object' && 'response' in err) {
      const axiosError = err as { response?: { data?: { detail?: string } } }
      error.value = axiosError.response?.data?.detail || '登录失败'
    } else if (err instanceof Error) {
      error.value = err.message
    } else {
      error.value = '登录失败'
    }
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  padding: var(--sp-5);
  background: var(--ink-900);
}

.login-container {
  width: 100%;
  display: flex;
  justify-content: center;
}

.login-card {
  width: 100%;
  max-width: 400px;
  padding: var(--sp-8);
  background: var(--ink-800);
  border-radius: var(--r-lg);
  border: 1px solid var(--border);
  color: var(--text-100);
  position: relative;
  z-index: 1;
}

.card-header {
  margin-bottom: var(--sp-6);
}

.logo {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border-radius: var(--r-sm);
  background: var(--accent);
  color: var(--ink-900);
  margin-bottom: var(--sp-4);
}

.logo svg {
  width: 22px;
  height: 22px;
}

.card-header h2 {
  font-weight: 600;
  font-size: var(--fs-xl);
  letter-spacing: -0.01em;
  margin-bottom: var(--sp-1);
  text-wrap: balance;
}

.subtitle {
  color: var(--text-300);
  font-size: var(--fs-sm);
  line-height: 1.5;
}

.login-form {
  display: flex;
  flex-direction: column;
  gap: var(--sp-4);
}

.form-group {
  width: 100%;
}

.input-label {
  display: flex;
  flex-direction: column;
  gap: var(--sp-1);
}

.label-text {
  font-weight: 500;
  font-size: var(--fs-xs);
  color: var(--text-300);
}

.form-input {
  width: 100%;
  padding: var(--sp-2) var(--sp-3);
  border-radius: var(--r-sm);
  background: var(--ink-900);
  color: var(--text-100);
  font-size: var(--fs-base);
  font-family: var(--font-body);
  outline: none;
  border: 1px solid var(--border);
  transition: border-color var(--dur-fast) var(--ease);
}

.form-input:focus-visible {
  border-color: var(--border-strong);
  outline: 2px solid var(--accent-line);
  outline-offset: 1px;
}

.form-input::placeholder {
  color: var(--text-400);
}

.form-input:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.error-message {
  background: var(--danger-wash);
  border: 1px solid var(--danger);
  color: var(--text-100);
  padding: var(--sp-2) var(--sp-3);
  border-radius: var(--r-sm);
  font-size: var(--fs-sm);
  line-height: 1.5;
}

.error-shake {
  animation: shake 0.4s var(--ease);
}

@keyframes shake {
  0%,
  100% {
    transform: translateX(0);
  }
  25% {
    transform: translateX(-4px);
  }
  50% {
    transform: translateX(4px);
  }
  75% {
    transform: translateX(-2px);
  }
}

.submit-btn {
  width: 100%;
  padding: var(--sp-3);
  border: none;
  border-radius: var(--r-sm);
  background: var(--accent);
  color: var(--ink-900);
  font-size: var(--fs-base);
  font-weight: 600;
  font-family: var(--font-body);
  cursor: pointer;
  transition: background var(--dur-fast) var(--ease);
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--sp-2);
}

.submit-btn:hover:not(:disabled) {
  background: var(--accent-hover);
}

.submit-btn:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}

.submit-btn:active:not(:disabled) {
  background: var(--accent-dim);
}

.submit-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.loading-spinner {
  width: 14px;
  height: 14px;
  border: 2px solid var(--ink-900);
  border-radius: 50%;
  border-top-color: transparent;
  animation: spin 0.7s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.register-link {
  margin-top: var(--sp-5);
  color: var(--text-300);
  font-size: var(--fs-sm);
}

.link {
  color: var(--accent);
  font-weight: 500;
  text-decoration: none;
  border-bottom: 1px solid var(--accent-line);
}

.link:hover {
  color: var(--accent-hover);
}

.link:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}

@media (prefers-reduced-motion: reduce) {
  .loading-spinner {
    animation: none;
    border-top-color: var(--ink-900);
  }

  .error-shake {
    animation: none;
  }
}
</style>
