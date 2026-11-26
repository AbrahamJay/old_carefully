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
    loading: true,
    // AI 辅助：默认关闭，status 接口不可用时静默降级
    agentEnabled: false,
    prepItems: [],
    agentBusy: false,
    // 润色会覆盖输入框原文，留一份用于撤销
    polishedFrom: ''
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
      if (order.status === 'assigned' || order.status === 'in_service') {
        this.initAgent()
      }
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
  // 手动改动输入框后，撤销润色就失效了
  onContent(e) { this.setData({ content: e.detail.value, polishedFrom: '' }) },
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
  // ---- AI 辅助（可选能力，任何失败都静默降级，不影响手工填写）----
  // 探测后端 Agent 开关；关闭或接口异常时保持 agentEnabled=false
  async initAgent() {
    try {
      const status = await request('/agent/status', { silent: true })
      const enabled = !!(status && status.enabled)
      this.setData({ agentEnabled: enabled })
      if (!enabled) return
      if (this.data.isAssigned || this.data.isInService) await this.loadPrepBrief()
    } catch (e) {
      this.setData({ agentEnabled: false })
    }
  },
  // 服务前提示：后端已做脱敏与条数限制，这里只负责展示
  async loadPrepBrief() {
    try {
      const data = await request('/agent/staff/prep-brief', {
        method: 'POST',
        data: { order_id: this.data.id },
        silent: true
      })
      this.setData({ prepItems: (data && data.items) || [] })
    } catch (e) {
      this.setData({ prepItems: [] })
    }
  },
  // 把后端 warnings 码位翻译成员工能看懂的一句话
  warningText(code) {
    const map = {
      redline: '检测到紧急情况，请先联系家属与站点，再手工记录',
      bad_output: 'AI 输出未能解析，请手工补充',
      empty_content: 'AI 内容为空，请补充要点后重试',
      truncated: '内容过长已截断，请核对',
      medical_guard: '已移除涉及用药建议的表述，请核对'
    }
    if (code && code.indexOf('missing_section:') === 0) {
      return '缺少「' + code.split(':')[1] + '」，请补充'
    }
    return map[code] || ''
  },
  // 润色只改表达、不改事实，结果仍需人工核对；失败不改原文
  async polishContent() {
    const text = (this.data.content || '').trim()
    if (!text || this.data.agentBusy) return
    // 后端 rough_notes 限 500 字，先在前端拦住
    if (text.length > 500) {
      wx.showToast({ title: '超过 500 字，先精简再润色', icon: 'none' })
      return
    }
    this.setData({ agentBusy: true })
    try {
      const data = await request('/agent/staff/record-draft', {
        method: 'POST',
        data: {
          order_id: this.data.id,
          rough_notes: text,
          photo_count: this.data.photos.length
        }
      })
      if (!data || !data.content) {
        wx.showToast({ title: '润色结果为空，已保留你写的内容', icon: 'none' })
        return
      }
      this.setData({ polishedFrom: this.data.content, content: data.content })
      const warnings = (data.warnings || []).map(code => this.warningText(code)).filter(Boolean)
      wx.showToast({ title: warnings[0] || '已润色，请核对后提交', icon: 'none' })
    } catch (e) {
      // request 已统一提示错误；润色失败时员工仍可手工填写
    } finally {
      this.setData({ agentBusy: false })
    }
  },
  undoPolish() {
    if (!this.data.polishedFrom) return
    this.setData({ content: this.data.polishedFrom, polishedFrom: '' })
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
      this.setData({ content: '', polishedFrom: '', photos: [], canAddPhoto: true })
      await this.load()
    } finally {
      this.setData({ submitting: false })
    }
  }
})
