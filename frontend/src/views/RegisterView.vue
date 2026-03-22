<template>
  <div class="register-page">
    <!-- 装饰元素 -->
    <div class="decorative-element top-right"></div>
    <div class="decorative-element bottom-left"></div>

    <div class="register-card" @mouseenter="cardHover = true" @mouseleave="cardHover = false">
      <div class="card-header">
        <div class="logo">🚂</div>
        <h2>创建账号</h2>
        <p class="subtitle">加入铁路历史专家的问答社区</p>
      </div>

      <form @submit.prevent="handleSubmit" class="register-form">
        <div class="form-group">
          <label class="input-label">
            <span class="label-text">用户名</span>
            <input
              v-model="form.username"
              type="text"
              required
              class="form-input"
              placeholder="请设置用户名"
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
              placeholder="请设置密码（至少6位）"
              :class="{ 'input-focus': passwordFocus }"
              @focus="passwordFocus = true"
              @blur="passwordFocus = false"
            />
          </label>
        </div>

        <div class="form-group">
          <label class="input-label">
            <span class="label-text">确认密码</span>
            <input
              v-model="form.confirmPassword"
              type="password"
              required
              class="form-input"
              placeholder="请再次输入密码"
              :class="{ 'input-focus': confirmFocus }"
              @focus="confirmFocus = true"
              @blur="confirmFocus = false"
            />
          </label>
        </div>

        <div v-if="error" class="error-message" :class="{ 'error-shake': errorShake }">
          {{ error }}
        </div>

        <button type="submit" class="submit-btn" :disabled="loading">
          <span v-if="loading" class="loading-spinner"></span>
          <span class="btn-text">{{ loading ? '注册中...' : '注册' }}</span>
        </button>

        <p class="login-link">已有账号？<router-link to="/login" class="link">登录</router-link></p>
      </form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const authStore = useAuthStore()
const router = useRouter()

// 表单状态
const form = ref({ username: '', password: '', confirmPassword: '' })
const error = ref('')
const loading = ref(false)
const cardHover = ref(false)
const usernameFocus = ref(false)
const passwordFocus = ref(false)
const confirmFocus = ref(false)
const errorShake = ref(false)

async function handleSubmit() {
  // 密码验证
  if (form.value.password.length < 6) {
    error.value = '密码长度不能少于6位'
    errorShake.value = true
    setTimeout(() => (errorShake.value = false), 500)
    return
  }

  if (form.value.password !== form.value.confirmPassword) {
    error.value = '两次输入的密码不一致'
    errorShake.value = true
    setTimeout(() => (errorShake.value = false), 500)
    return
  }

  error.value = ''
  loading.value = true

  try {
    await authStore.register({
      username: form.value.username,
      password: form.value.password,
    })
    router.push('/chat')
  } catch (err: unknown) {
    // 错误处理
    errorShake.value = true
    setTimeout(() => (errorShake.value = false), 500)

    if (err && typeof err === 'object' && 'response' in err) {
      const axiosError = err as { response?: { data?: { detail?: string } } }
      error.value = axiosError.response?.data?.detail || '注册失败'
    } else if (err instanceof Error) {
      error.value = err.message
    } else {
      error.value = '注册失败'
    }
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.register-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  padding: 20px;
  overflow: hidden;
}

/* 装饰元素 */
.decorative-element {
  position: absolute;
  width: 400px;
  height: 400px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.05);
  filter: blur(80px);
  z-index: 0;
}

.top-right {
  top: -200px;
  right: -200px;
}

.bottom-left {
  bottom: -200px;
  left: -200px;
}

.register-card {
  width: 100%;
  max-width: 420px;
  padding: 2.5rem;
  background: rgba(255, 255, 255, 0.1);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border-radius: 24px;
  box-shadow:
    0 8px 32px rgba(0, 0, 0, 0.1),
    0 1px 2px rgba(0, 0, 0, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.2);
  color: #fff;
  position: relative;
  z-index: 1;
  transition: all 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275);
}

.register-card:hover {
  transform: translateY(-5px);
  box-shadow:
    0 12px 40px rgba(0, 0, 0, 0.15),
    0 2px 4px rgba(0, 0, 0, 0.1);
  border-color: rgba(255, 255, 255, 0.3);
}

.card-header {
  text-align: center;
  margin-bottom: 2rem;
}

.logo {
  font-size: 2.5rem;
  margin-bottom: 0.8rem;
  animation: bounce 2s infinite alternate;
}

@keyframes bounce {
  from {
    transform: scale(1);
  }
  to {
    transform: scale(1.05);
  }
}

.card-header h2 {
  font-weight: 600;
  font-size: 1.8rem;
  letter-spacing: 0.5px;
  margin-bottom: 0.5rem;
  text-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
}

.subtitle {
  color: rgba(255, 255, 255, 0.7);
  font-size: 0.9rem;
}

.register-form {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.form-group {
  width: 100%;
}

.input-label {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.label-text {
  font-weight: 500;
  font-size: 0.85rem;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: rgba(255, 255, 255, 0.8);
}

.form-input {
  width: 100%;
  padding: 0.9rem 1.2rem;
  border: none;
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.08);
  backdrop-filter: blur(4px);
  -webkit-backdrop-filter: blur(4px);
  color: white;
  font-size: 1rem;
  outline: none;
  transition: all 0.3s ease;
  border: 1px solid rgba(255, 255, 255, 0.1);
}

.form-input:focus {
  background: rgba(255, 255, 255, 0.12);
  border-color: rgba(255, 255, 255, 0.4);
  box-shadow: 0 0 0 3px rgba(255, 255, 255, 0.1);
}

.form-input::placeholder {
  color: rgba(255, 255, 255, 0.4);
}

.input-focus {
  background: rgba(255, 255, 255, 0.12);
}

.error-message {
  background: rgba(255, 80, 80, 0.2);
  backdrop-filter: blur(4px);
  -webkit-backdrop-filter: blur(4px);
  border: 1px solid rgba(255, 100, 100, 0.4);
  color: white;
  padding: 0.8rem 1.2rem;
  border-radius: 12px;
  text-align: center;
  font-size: 0.9rem;
  transition: all 0.3s ease;
}

.error-shake {
  animation: shake 0.5s ease-in-out;
}

@keyframes shake {
  0%,
  100% {
    transform: translateX(0);
  }
  20% {
    transform: translateX(-5px);
  }
  40% {
    transform: translateX(5px);
  }
  60% {
    transform: translateX(-3px);
  }
  80% {
    transform: translateX(3px);
  }
}

.submit-btn {
  width: 100%;
  padding: 0.9rem;
  border: none;
  border-radius: 16px;
  background: linear-gradient(135deg, rgba(139, 92, 246, 0.8), rgba(90, 103, 216, 0.8));
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  color: white;
  font-size: 1rem;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.3s ease;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  position: relative;
  overflow: hidden;
}

.submit-btn::after {
  content: '';
  position: absolute;
  top: 0;
  left: -100%;
  width: 100%;
  height: 100%;
  background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.2), transparent);
  transition: left 0.6s ease;
}

.submit-btn:hover:not(:disabled)::after {
  left: 100%;
}

.submit-btn:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 8px 20px rgba(139, 92, 246, 0.3);
}

.submit-btn:active:not(:disabled) {
  transform: scale(0.98) translateY(0);
}

.submit-btn:disabled {
  opacity: 0.7;
  cursor: not-allowed;
  transform: none;
  box-shadow: none;
}

.loading-spinner {
  width: 16px;
  height: 16px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-radius: 50%;
  border-top-color: white;
  animation: spin 1s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.login-link {
  text-align: center;
  margin-top: 1.5rem;
  color: rgba(255, 255, 255, 0.7);
  font-size: 0.9rem;
}

.link {
  color: white;
  font-weight: 600;
  text-decoration: none;
  position: relative;
}

.link::after {
  content: '';
  position: absolute;
  bottom: -2px;
  left: 0;
  width: 0;
  height: 2px;
  background: white;
  transition: width 0.3s ease;
}

.link:hover::after {
  width: 100%;
}

/* 响应式适配 */
@media (max-width: 480px) {
  .register-card {
    padding: 2rem 1.5rem;
  }

  .card-header h2 {
    font-size: 1.5rem;
  }
}
</style>
