import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'

// H5 与后台同域部署在不同路径：生产构建固定 base=/h5/（路由用 BASE_URL 拼前缀），
// 需要换挂载路径（例如 /m/）时用 VITE_BASE 覆盖。
// 开发期代理目标用 VITE_PROXY_TARGET 覆盖，默认值只面向本机。
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '.', 'VITE_')

  return {
    plugins: [vue()],
    base: mode === 'production' ? env.VITE_BASE || '/h5/' : '/',
    server: {
      port: 5174,
      host: '0.0.0.0',
      proxy: {
        '/api': {
          target: env.VITE_PROXY_TARGET || 'http://127.0.0.1:8000',
          changeOrigin: true
        }
      }
    }
  }
})
