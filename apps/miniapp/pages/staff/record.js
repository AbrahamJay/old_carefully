const { request, upload } = require('../../utils/request')
const { requireLogin } = require('../../utils/auth')
const { statusInfo, dateTime, photoUrl } = require('../../utils/format')

Page({
  data: {
    id: 0,
    order: null,
    statusText: '',
    statusCls: '',
    timeText: '',
    content: '',
    photos: [],
    records: [],
    allPhotos: [],
    canAddPhoto: true,
    isAssigned: false,
    isInService: false,
    isCompleted: false,
    uploading: false,
    submitting: false,
    loading: true
  },
  onLoad(options) {
    this.setData({ id: Number(options.id) })
  },
  onShow() {
    if (!requireLogin()) return
    this.load()
  },
  async onPullDownRefresh() {
    try {
      await this.load()
    } finally {
      wx.stopPullDownRefresh()
    }
  },
  async load() {
    this.setData({ loading: true })
    try {
      const order = await request('/orders/' + this.data.id)
      const status = statusInfo(order.status)
      const records = (order.records || []).map(record => ({
        ...record,
        timeText: dateTime(record.checkin_at),
        photos: (record.photos || []).map(photoUrl)
      }))
      const allPhotos = records.reduce((acc, item) => acc.concat(item.photos), [])
      this.setData({
        order: { ...order, records },
        records,
        allPhotos,
        statusText: status.text,
        statusCls: status.cls,
        timeText: dateTime(order.scheduled_at),
        isAssigned: order.status === 'assigned',
        isInService: order.status === 'in_service',
        isCompleted: order.status === 'completed',
        canAddPhoto: this.data.photos.length < 3
      })
    } finally {
      this.setData({ loading: false })
    }
  },
  copyOrderNo() {
    if (!this.data.order) return
    wx.setClipboardData({
      data: this.data.order.order_no,
      success: () => wx.showToast({ title: '订单号已复制', icon: 'none' })
    })
  },
  async acceptAndStart() {
    try {
      await request('/orders/' + this.data.id + '/accept', { method: 'POST' })
      await request('/orders/' + this.data.id + '/start', { method: 'POST' })
      wx.showToast({ title: '已开始服务', icon: 'success' })
      this.load()
    } catch (e) {
      // request toast
    }
  },
  onContent(e) { this.setData({ content: e.detail.value }) },
  chooseImage() {
    const left = 3 - this.data.photos.length
    if (left <= 0) return
    wx.chooseMedia({
      count: left,
      mediaType: ['image'],
      sourceType: ['camera', 'album'],
      success: async res => {
        this.setData({ uploading: true })
        wx.showLoading({ title: '上传中' })
        try {
          const photos = this.data.photos.slice()
          for (const file of res.tempFiles) {
            const data = await upload(file.tempFilePath)
            photos.push({ path: data.url, url: photoUrl(data.url) })
          }
          this.setData({ photos, canAddPhoto: photos.length < 3 })
        } finally {
          wx.hideLoading()
          this.setData({ uploading: false })
        }
      }
    })
  },
  removePhoto(e) {
    const index = Number(e.currentTarget.dataset.index)
    const photos = this.data.photos.slice()
    photos.splice(index, 1)
    this.setData({ photos, canAddPhoto: photos.length < 3 })
  },
  previewImage(e) {
    const current = e.currentTarget.dataset.url
    const urls = this.data.allPhotos.length
      ? this.data.allPhotos
      : this.data.photos.map(item => item.url)
    wx.previewImage({ current, urls })
  },
  async submit() {
    if (!this.data.content && !this.data.photos.length) {
      wx.showToast({ title: '写两句或上传照片', icon: 'none' })
      return
    }
    this.setData({ submitting: true })
    try {
      await request('/orders/' + this.data.id + '/records', {
        method: 'POST',
        data: {
          content: this.data.content || '已上传服务照片',
          photos: this.data.photos.map(item => item.path),
          elder_confirmed: false
        }
      })
      await request('/orders/' + this.data.id + '/complete', { method: 'POST' })
      wx.showToast({ title: '已完成', icon: 'success' })
      this.setData({ content: '', photos: [], canAddPhoto: true })
      await this.load()
    } finally {
      this.setData({ submitting: false })
    }
  }
})
