const { API_BASE } = require('./config')

function getToken() {
  return wx.getStorageSync('token') || ''
}

function request(path, options = {}) {
  const method = options.method || 'GET'
  const data = options.data || {}
  const auth = options.auth !== false
  // silent=true 时不弹 toast：用于 AI 状态探测等可选能力，失败需静默降级
  const silent = options.silent === true
  return new Promise((resolve, reject) => {
    const header = { 'Content-Type': 'application/json' }
    if (auth && getToken()) header.Authorization = 'Bearer ' + getToken()
    wx.request({
      url: API_BASE + path,
      method,
      data,
      header,
      success(res) {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(res.data)
          return
        }
        if (res.statusCode === 401) {
          wx.removeStorageSync('token')
          wx.removeStorageSync('user')
          wx.reLaunch({ url: '/pages/login/index' })
          reject(res.data)
          return
        }
        const detail = res.data && (res.data.detail || res.data.message)
        if (!silent) {
          wx.showToast({ title: typeof detail === 'string' ? detail : '请求失败', icon: 'none' })
        }
        reject(res.data)
      },
      fail(err) {
        console.error('[request fail]', path, err)
        const errMsg = (err && err.errMsg) || ''
        let tip = '网络失败：检查后端'
        if (errMsg.indexOf('domain') >= 0) tip = '域名校验失败'
        else if (errMsg.indexOf('timeout') >= 0) tip = '请求超时'
        else if (errMsg.indexOf('127.0.0.1') >= 0) tip = '真机不能用127.0.0.1'
        if (!silent) {
          wx.showToast({ title: tip, icon: 'none' })
        }
        reject(err)
      }
    })
  })
}

function upload(filePath) {
  return new Promise((resolve, reject) => {
    wx.uploadFile({
      url: API_BASE + '/uploads',
      filePath,
      name: 'file',
      header: { Authorization: 'Bearer ' + getToken() },
      success(res) {
        let data = {}
        try { data = JSON.parse(res.data) } catch (e) { data = {} }
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(data)
        } else {
          wx.showToast({ title: data.detail || '上传失败', icon: 'none' })
          reject(data)
        }
      },
      fail(err) {
        wx.showToast({ title: '上传失败', icon: 'none' })
        reject(err)
      }
    })
  })
}

module.exports = { request, upload, getToken }
