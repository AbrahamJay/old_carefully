const { request } = require('../../utils/request')
const { setLogin, getUser } = require('../../utils/auth')
const { DEFAULT_CUSTOMER_PHONE, DEFAULT_STAFF_PHONE, DEFAULT_PASSWORD } = require('../../utils/config')

Page({
  data: {
    phone: DEFAULT_CUSTOMER_PHONE,
    password: DEFAULT_PASSWORD,
    role: 'customer',
    loading: false
  },
  onLoad() {
    const user = getUser()
    if (user) this.redirect(user)
  },
  onPhone(e) { this.setData({ phone: e.detail.value }) },
  onPassword(e) { this.setData({ password: e.detail.value }) },
  selectRole(e) {
    const role = e.currentTarget.dataset.role
    this.setData({
      role,
      phone: role === 'staff' ? DEFAULT_STAFF_PHONE : DEFAULT_CUSTOMER_PHONE,
      password: DEFAULT_PASSWORD
    })
  },
  async submit() {
    if (!this.data.phone) {
      wx.showToast({ title: '请输入手机号', icon: 'none' })
      return
    }
    if (!this.data.password) {
      wx.showToast({ title: '请输入密码', icon: 'none' })
      return
    }
    this.setData({ loading: true })
    try {
      const data = await request('/auth/login', {
        method: 'POST',
        auth: false,
        data: { phone: this.data.phone, password: this.data.password }
      })
      const roleText = { customer: '家属', staff: '服务人员' }[data.user.role]
      if (!roleText) {
        wx.showModal({ title: '无法登录', content: '该账号不能登录小程序', showCancel: false })
        return
      }
      if (data.user.role !== this.data.role) {
        wx.showModal({
          title: '身份不匹配',
          content: '该账号是' + roleText + '账号，请选择“我是' + roleText + '”登录',
          showCancel: false
        })
        return
      }
      setLogin(data)
      wx.showToast({ title: '欢迎回来', icon: 'success' })
      setTimeout(() => this.redirect(data.user), 260)
    } catch (e) {
      // toast already shown by request
    } finally {
      this.setData({ loading: false })
    }
  },
  redirect(user) {
    if (user.role === 'staff') {
      wx.redirectTo({ url: '/pages/staff/orders' })
    } else {
      wx.switchTab({ url: '/pages/home/index' })
    }
  }
})
