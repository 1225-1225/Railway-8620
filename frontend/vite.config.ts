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
      // /chat/ 开头的子路径（stream、sessions）全部代理
      '/chat/': 'http://localhost:8000',
      // /chat 本身：仅 POST（非流式接口）代理，GET 由 SPA 处理
      '/chat': {
        target: 'http://localhost:8000',
        bypass(req) {
          if (req.method !== 'POST') {
            return '/index.html'
          }
        },
      },
      // /maps 开头的路径代理到后端（地图静态文件）
      '/maps': 'http://localhost:8000',
    },
  },
})
