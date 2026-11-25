// 后端地址：全项目只在这里改，其余页面都从本文件取。
//
// 三种场景取值不同，不要混用：
//   1) 微信开发者工具 / 模拟器：http://120.53.13.162        （云服务器，走 nginx 80）
//   2) 真机预览：同一地址，但需在开发者工具里勾「不校验合法域名、web-view（业务域名）、
//      TLS 版本以及 HTTPS 证书」，且手机能访问公网 80 端口
//   3) 正式发布：必须是已备案的 HTTPS 域名（如 https://yanglao.example.com），
//      并在微信公众平台「开发管理 → 服务器域名」把它加入 request 合法域名；
//      要求 HTTPS + 备案域名，IP 与 http 均不被允许
//   4) 纯本机联调：http://127.0.0.1:8000（后端 uvicorn --host 0.0.0.0）
const HOST = 'http://120.53.13.162'

module.exports = {
  HOST,
  API_BASE: HOST + '/api/v1',
  SERVICE_PHONE: '0731-0000000',
  DEFAULT_CUSTOMER_PHONE: '13907320001',
  DEFAULT_STAFF_PHONE: '17352680001',
  DEFAULT_PASSWORD: '123456',
  EMERGENCY_PHONE: '120'
}
