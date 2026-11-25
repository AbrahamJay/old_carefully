const { request } = require('../../utils/request')
const { requireLogin, getUser } = require('../../utils/auth')

Page({
  data: { elders: [], loading: true, isStaff: false },
  onShow() {
    if (!requireLogin()) return
    const user = getUser() || {}
    this.setData({ isStaff: user.role === 'staff' })
    this.load()
  },
  async load() {
    this.setData({ loading: true })
    try {
      const elders = await request('/elders')
      this.setData({ elders: elders.map(item => ({ ...item, avatarText: item.name ? item.name[0] : '老' })) })
    } finally {
      this.setData({ loading: false })
    }
  },
  onElderTap(e) {
    const index = Number(e.currentTarget.dataset.index)
    const elder = this.data.elders[index]
    if (!elder) return
    if (this.data.isStaff) {
      wx.showModal({
        title: elder.name,
        content: '服务地址：' + (elder.address || '未填') + '\n联系电话：' + (elder.phone || elder.emergency_phone || '未填') + '\n照护备注：' + (elder.health_notes || '无'),
        showCancel: false,
        confirmText: '知道了'
      })
      return
    }
    wx.navigateTo({ url: '/pages/elder/edit?id=' + elder.id })
  },
  goAdd() {
    if (this.data.isStaff) {
      wx.showToast({ title: '员工端不需要新增档案', icon: 'none' })
      return
    }
    wx.navigateTo({ url: '/pages/elder/edit' })
  },
  copyInvite(e) {
    const code = e.currentTarget.dataset.code
    if (!code) return
    wx.setClipboardData({
      data: code,
      success: () => wx.showToast({ title: '邀请码已复制', icon: 'none' })
    })
  },
  goBind() {
    if (this.data.isStaff) {
      wx.showToast({ title: '员工端不需要绑定长辈', icon: 'none' })
      return
    }
    wx.navigateTo({ url: '/pages/elder/bind' })
  }
})
