import axios from 'axios'
import router from '@/router'
import { isTokenExpired } from '@/stores/auth'

const api = axios.create({
  baseURL: '',  // 空 = 相对路径：Docker 中 nginx 代理；本地开发用 Vite proxy
  timeout: 60000,  // 路线图绘制可能较慢
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
