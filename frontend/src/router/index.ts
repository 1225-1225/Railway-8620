import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'

// 导入组件（使用动态导入）
const LoginView = () => import('../views/LoginView.vue')
const RegisterView = () => import('../views/RegisterView.vue')
const ChatView = () => import('../views/ChatLegacyView.vue') // 原非流式页面
const ChatStreamView = () => import('../views/ChatView.vue') // 流式页面

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      redirect: '/chat', // 默认重定向到流式聊天页
    },
    {
      path: '/login',
      name: 'login',
      component: LoginView,
      meta: { requiresGuest: true }, // 仅未登录可访问
    },
    {
      path: '/register',
      name: 'register',
      component: RegisterView,
      meta: { requiresGuest: true },
    },
    {
      path: '/chat',
      name: 'chat',
      component: ChatStreamView, // 流式版本
      meta: { requiresAuth: true }, // 需要登录
    },
    {
      path: '/chat/legacy',
      name: 'chat-legacy',
      component: ChatView, // 原非流式版本
      meta: { requiresAuth: true },
    },
    // 通配符路由：所有未匹配的路径都重定向到登录页
    {
      path: '/:pathMatch(.*)*',
      redirect: '/login',
    },
  ],
})

// 路由守卫：只要令牌过期或不存在，无论什么路径都跳转到登录页
// 白名单：无需登录即可访问的路径
const WHITELIST = ['/login', '/register']

router.beforeEach((to, _from, next) => {
  const authStore = useAuthStore()

  // 白名单路径直接放行（登录/注册页）
  if (WHITELIST.includes(to.path)) {
    // 已登录用户访问登录/注册页 → 跳转到聊天页
    if (authStore.isLoggedIn) {
      next('/chat')
      return
    }
    next()
    return
  }

  // 非白名单路径：检查令牌是否有效
  if (!authStore.isLoggedIn) {
    // 令牌不存在或已过期 → 强制跳转登录页
    authStore.logout()
    next({ path: '/login', query: { redirect: to.fullPath } })
    return
  }

  next()
})

export default router
