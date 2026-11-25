<template>
  <main class="page no-tab">
    <header class="topbar">
      <button class="back" @click="router.back()">‹</button>
      <span class="topbar-title">紧急联系</span>
      <span class="topbar-space"></span>
    </header>
    <div class="page-intro">
      <span class="eyebrow">EMERGENCY</span>
      <h1>紧急联系</h1>
      <p>如遇摔倒、胸痛、呼吸困难等紧急情况，请先拨打 120。</p>
    </div>
    <section class="emergency-hero">
      <span>急救电话</span>
      <strong>120</strong>
      <a class="btn btn-primary" href="tel:120">拨打 120</a>
    </section>
    <section class="card organic">
      <button class="call-item" @click="call(SERVICE_PHONE)"><span><b>社区养老管家</b><small>{{ SERVICE_PHONE }}</small></span><span class="call-btn">拨打</span></button>
      <button class="call-item" @click="call('0731-0000000')"><span><b>社区服务中心</b><small>0731-0000000</small></span><span class="call-btn">拨打</span></button>
    </section>
    <section class="card warm"><h2 class="section-title">重要说明</h2><p class="small muted mt8">本演示版不提供急救承诺，不替代 120、社区和家属的应急处理。</p></section>
  </main>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'
import { SERVICE_PHONE } from '../constants'
const router = useRouter()
function call(phone: string) { location.href = 'tel:' + phone }
</script>

<style scoped>
.page-intro { margin: 0 2px 14px; }
.page-intro h1 { margin: 6px 0 0; font-size: 26px; }
.page-intro p { margin: 4px 0 0; font-size: 11px; line-height: 1.7; color: var(--muted); }
.emergency-hero { position: relative; overflow: hidden; border-radius: 26px 20px 28px 20px; padding: 18px 20px; margin-bottom: 12px; background: linear-gradient(135deg, #FFF6EE, #FCE7DA); color: #A95522; }
.emergency-hero span { font-size: 10px; }
.emergency-hero strong { display: block; margin: 4px 0 12px; font-size: 44px; line-height: 1; color: #C93B2B; }
.emergency-hero a { display: inline-block; padding: 10px 20px; border-radius: 999px; font-size: 12px; }
.call-item { width: 100%; display: flex; align-items: center; justify-content: space-between; padding: 14px 0; border: none; border-bottom: 1px solid var(--line); background: transparent; text-align: left; }
.call-item:last-child { border-bottom: none; }
.call-item b { display: block; font-size: 13px; }
.call-item small { display: block; margin-top: 2px; font-size: 10px; color: var(--muted); }
.call-btn { padding: 7px 14px; border-radius: 999px; background: var(--soft); color: var(--primary); font-size: 10px; font-weight: 700; }
</style>
