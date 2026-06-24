import axios from 'axios'
import router from '@/router'

// 解析 JWT payload，返回对象或 null
function parseJwtPayload(token: string): Record<string, unknown> | null {
  try {
    const parts = token.split('.')
    if (parts.length !== 3) {
      return null
    }
    const base64Url = parts[1]
    // eslint-disable-next-line @typescript-eslint/ban-ts-comment
    // @ts-expect-error
    const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/')
    const jsonPayload = decodeURIComponent(
      atob(base64)
        .split('')
        .map((c) => '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2))
        .join(''),
    )
    return JSON.parse(jsonPayload)
  } catch (e) {
    console.error('解析 token 失败', e)
    return null
  }
}

const api = axios.create({
  baseURL: '',  // 空 = 相对路径：Docker 中 nginx 代理；本地开发用 Vite proxy
  timeout: 30000,
})

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) {
    const payload = parseJwtPayload(token)
    if (payload && typeof payload.exp === 'number') {
      const expTime = payload.exp * 1000
      const now = Date.now()
      if (expTime < now) {
        localStorage.removeItem('token')
        localStorage.removeItem('username')
        if (router.currentRoute.value.path !== '/login') {
          router.push('/login')
        }
        throw new Error('Token 已过期，请重新登录')
      }
    }
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

api.interceptors.response.use(
  (response) => response,
  (error) => {
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
