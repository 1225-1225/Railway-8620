import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api from '@/services/api'

// 解析 JWT payload，返回对象或 null
function parseJwtPayload(token: string): Record<string, unknown> | null {
  try {
    const parts = token.split('.')
    if (parts.length !== 3) return null
    const base64 = parts[1].replace(/-/g, '+').replace(/_/g, '/')
    const jsonPayload = decodeURIComponent(
      atob(base64)
        .split('')
        .map((c) => '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2))
        .join(''),
    )
    return JSON.parse(jsonPayload)
  } catch {
    return null
  }
}

/** 检查令牌是否已过期（提前 10 秒判定，避免边缘情况） */
export function isTokenExpired(token: string): boolean {
  const payload = parseJwtPayload(token)
  if (!payload || typeof payload.exp !== 'number') {
    // 无法解析的 token 视为已过期
    return true
  }
  // 提前 10 秒判定过期，避免请求发出瞬间刚好过期
  return payload.exp * 1000 < Date.now() - 10_000
}

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem('token') || '')
  const username = ref(localStorage.getItem('username') || '')

  const isLoggedIn = computed(() => {
    if (!token.value) return false
    return !isTokenExpired(token.value)
  })

  function setToken(newToken: string) {
    token.value = newToken
    localStorage.setItem('token', newToken)
  }

  function setUsername(newUsername: string) {
    username.value = newUsername
    localStorage.setItem('username', newUsername)
  }

  async function login(loginData: { username: string; password: string }) {
    const formData = new FormData()
    formData.append('username', loginData.username)
    formData.append('password', loginData.password)

    const res = await api.post('/auth/login', formData)
    setToken(res.data.access_token)
    setUsername(loginData.username)
  }

  async function register(registerData: { username: string; password: string }) {
    // 注册接口直接返回 token，无需再调用登录
    const res = await api.post('/auth/register', registerData)
    setToken(res.data.access_token)
    setUsername(registerData.username)
  }

  function logout() {
    token.value = ''
    username.value = ''
    localStorage.removeItem('token')
    localStorage.removeItem('username')
  }

  return {
    token,
    username,
    isLoggedIn,
    login,
    register,
    logout,
  }
})
