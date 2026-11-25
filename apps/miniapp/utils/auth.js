function getUser() {
  return wx.getStorageSync('user') || null
}

function setLogin(data) {
  wx.setStorageSync('token', data.access_token)
  wx.setStorageSync('user', data.user)
}

function logout() {
  wx.removeStorageSync('token')
  wx.removeStorageSync('user')
  wx.reLaunch({ url: '/pages/login/index' })
}

function requireLogin() {
  if (!wx.getStorageSync('token')) {
    wx.reLaunch({ url: '/pages/login/index' })
    return false
  }
  return true
}

module.exports = { getUser, setLogin, logout, requireLogin }
