import axios from 'axios'
import router from '@/router'
import { isTokenExpired } from '@/stores/auth'

/**
 * 全局 HTTP 客户端（axios 实例）
 *
 * 项目约定：**除 SSE 流式接口外，所有请求都走这里**，不再直接用 fetch。
 * 统一走拦截器意味着 token 注入、过期检查、401 跳登录只有一份实现。
 *
 * 唯一的例外是 `/chat/stream`（SSE）：浏览器里 axios 基于 XHR，
 * 拿不到 ReadableStream，无法逐块读取响应体；必须用 fetch + response.body.getReader()。
 * 该处需要手动带 Authorization 头（不经过拦截器）。
 */
const api = axios.create({
  baseURL: '', // 空 = 相对路径：Docker 中 nginx 代理；本地开发用 Vite proxy
  timeout: 60000, // 路线图绘制可能较慢
})

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) {
    // 令牌过期 → 清除并跳转登录
    if (isTokenExpired(token)) {
      localStorage.removeItem('token')
      localStorage.removeItem('username')
      if (router.currentRoute.value.path !== '/login') {
        router.push('/login')
      }
      return Promise.reject(new axios.Cancel('Token expired'))
    }
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

api.interceptors.response.use(
  (response) => response,
  (error) => {
    // 服务端返回 401 → 清除并跳转登录
    if (error.response && error.response.status === 401) {
      localStorage.removeItem('token')
      localStorage.removeItem('username')
      if (router.currentRoute.value.path !== '/login') {
        router.push('/login')
      }
    }
    return Promise.reject(error)
  },
)

export default api
