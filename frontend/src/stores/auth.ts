import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api from '@/services/api'

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem('token') || '')
  const username = ref(localStorage.getItem('username') || '')

  const isLoggedIn = computed(() => !!token.value)

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
