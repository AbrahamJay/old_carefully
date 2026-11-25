const { request } = require('./request')
const { money } = require('./format')

let checking = false

function findUnpaid(orders) {
  return (orders || []).find(
    item => Number(item.remaining_cents || 0) > 0 && item.payment_status !== 'refunded'
  )
}

// 在跳转预约页之前检查尾款，避免先跳页再弹窗。
function guardCreateOrder(onPass) {
  if (checking) return
  checking = true
  wx.showLoading({ title: '检查支付状态', mask: true })
  request('/orders?status=completed&page_size=100')
    .then(data => {
      wx.hideLoading()
      const unpaid = findUnpaid(data && data.items)
      if (!unpaid) {
        onPass()
        return
      }
      wx.showModal({
        title: '有未结清尾款',
        content: '订单 ' + unpaid.order_no + ' 还有 ¥' + money(unpaid.remaining_cents) + ' 尾款，请先结清后再预约。',
        confirmText: '去支付',
        cancelText: '取消',
        success: res => {
          if (res.confirm) {
            wx.navigateTo({ url: '/pages/order/detail?id=' + unpaid.id })
          }
        }
      })
    })
    .catch(() => {
      wx.hideLoading()
      wx.showToast({ title: '检查支付状态失败，请重试', icon: 'none' })
    })
    .finally(() => {
      checking = false
    })
}

module.exports = { guardCreateOrder }
