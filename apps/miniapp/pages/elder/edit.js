const { request } = require('../../utils/request')
const { requireLogin } = require('../../utils/auth')

Page({
  data: {
    id: 0,
    form: {
      name: '',
      phone: '',
      address: '',
      community: '',
      health_notes: '',
      emergency_name: '',
      emergency_phone: '',
      station_id: null
    },
    stations: [],
    stationIndex: 0,
    stationName: '',
    agreed: false,
    loading: false
  },
  onLoad(options) {
    if (!requireLogin()) return
    const id = options.id ? Number(options.id) : 0
    this.setData({ id })
    this.init(id)
  },
  async init(id) {
    const stations = await request('/stations')
    let form = { ...this.data.form, station_id: stations[0] ? stations[0].id : null }
    if (id) {
      const elder = await request('/elders/' + id)
      form = { ...form, ...elder }
      if (!form.station_id && stations[0]) form.station_id = stations[0].id
    }
    let stationIndex = stations.findIndex(item => item.id === form.station_id)
    if (stationIndex < 0) stationIndex = 0
    this.setData({
      stations,
      stationIndex,
      stationName: stations[stationIndex] ? stations[stationIndex].name : '',
      form,
      agreed: id ? true : this.data.agreed
    })
  },
  onInput(e) {
    const field = e.currentTarget.dataset.field
    this.setData({ ['form.' + field]: e.detail.value })
  },
  onStationChange(e) {
    const index = Number(e.detail.value)
    const station = this.data.stations[index]
    this.setData({
      stationIndex: index,
      stationName: station ? station.name : '',
      'form.station_id': station ? station.id : null
    })
  },
  onAgree(e) { this.setData({ agreed: e.detail.value.length > 0 }) },
  async save() {
    if (!this.data.form.name) {
      wx.showToast({ title: '请填写老人姓名', icon: 'none' })
      return
    }
    if (!this.data.form.station_id) {
      wx.showToast({ title: '请选择服务区域', icon: 'none' })
      return
    }
    if (!this.data.agreed) {
      wx.showToast({ title: '请勾选授权确认', icon: 'none' })
      return
    }
    this.setData({ loading: true })
    try {
      let elder
      if (this.data.id) {
        elder = await request('/elders/' + this.data.id, { method: 'PATCH', data: this.data.form })
      } else {
        elder = await request('/elders', { method: 'POST', data: this.data.form })
        await request('/elders/' + elder.id + '/consents', {
          method: 'POST',
          data: { type: 'service', version: 'v1', signed_by: '家属' }
        })
      }
      wx.showToast({ title: '已保存', icon: 'success' })
      setTimeout(() => wx.navigateBack(), 400)
    } finally {
      this.setData({ loading: false })
    }
  }
})
