import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  css: {
    preprocessorOptions: {
      less: {
        // 让每个 SFC 的 <style lang="less"> 都能直接用混入，无需逐个 import
        additionalData: '@import "@/styles/mixins.less";',
        javascriptEnabled: true,
      },
    },
  },
  server: {
    port: 5173,
    proxy: {
      // SSE（stream=true 时响应为 text/event-stream）经此代理不会被缓冲
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
