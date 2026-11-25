// 全局数据：后端地址统一从 utils/config.js 取，避免两处地址不一致
const { HOST, API_BASE } = require('./utils/config')

App({
  globalData: {
    host: HOST,
    apiBase: API_BASE,
    user: null
  },
  onLaunch() {
    this.globalData.user = wx.getStorageSync('user') || null
  }
})
