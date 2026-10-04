import { fileURLToPath, URL } from 'node:url'

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import vueDevTools from 'vite-plugin-vue-devtools'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    vue(),
    vueDevTools(),
  ],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url))
    },
  },
  server: {
    port: 8620,
    proxy: {
      '/auth': 'http://localhost:8000',
      // /chat/ 开头的子路径（stream、sessions）全部代理到后端
      '/chat/': 'http://localhost:8000',
      // 注意：不要给 /chat（不带斜杠）配代理。它既是前端路由页面，
      // 又不再对应任何后端接口（旧的非流式 POST /chat 已删除），
      // 交给 Vite 的 SPA fallback 返回 index.html 即可。
      // /maps 开头的路径代理到后端（地图静态文件）
      '/maps': 'http://localhost:8000',
    },
  },
})
