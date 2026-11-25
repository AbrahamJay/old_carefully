import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'

// 管理后台部署在站点根路径（base=/），所以不需要配 base。
// 开发期代理目标用 VITE_PROXY_TARGET 覆盖，默认值只面向本机，避免把服务器地址写死进仓库：
//   echo 'VITE_PROXY_TARGET=http://120.53.13.162' > .env.local
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '.', 'VITE_')

  return {
    plugins: [vue()],
    server: {
      port: 5173,
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
