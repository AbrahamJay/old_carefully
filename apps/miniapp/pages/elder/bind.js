const { request } = require('../../utils/request')
const { requireLogin } = require('../../utils/auth')

Page({
  data: { inviteCode: '', loading: false },
  onShow() { requireLogin() },
  goAdd() { wx.redirectTo({ url: '/pages/elder/edit' }) },
  onInput(e) { this.setData({ inviteCode: e.detail.value.toUpperCase() }) },
  async submit() {
    if (!this.data.inviteCode) {
      wx.showToast({ title: '请输入邀请码', icon: 'none' })
      return
    }
    this.setData({ loading: true })
    try {
      await request('/bindings', {
        method: 'POST',
        data: { invite_code: this.data.inviteCode, relation: 'family' }
      })
      wx.showToast({ title: '绑定成功', icon: 'success' })
      setTimeout(() => wx.navigateBack(), 400)
    } finally {
      this.setData({ loading: false })
    }
  }
})
