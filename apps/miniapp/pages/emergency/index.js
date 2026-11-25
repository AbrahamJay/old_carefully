const { SERVICE_PHONE, EMERGENCY_PHONE } = require('../../utils/config')

Page({
  data: { servicePhone: SERVICE_PHONE, emergencyPhone: EMERGENCY_PHONE, communityPhone: '0731-0000001' },
  call(e) {
    const phone = e.currentTarget.dataset.phone
    wx.makePhoneCall({ phoneNumber: phone })
  }
})
