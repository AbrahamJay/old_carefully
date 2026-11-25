<template>
  <main class="page no-tab">
    <header class="topbar">
      <button class="back" @click="router.back()">‹</button>
      <span class="topbar-title">隐私政策</span>
      <span class="topbar-space"></span>
    </header>
    <div class="page-intro">
      <span class="eyebrow">PRIVACY</span>
      <h1>隐私政策与授权</h1>
      <p>演示版 · 更新日期 2026-11</p>
    </div>
    <section class="card organic">
      <h2 class="section-title">我们收集什么</h2>
      <p>为了提供上门服务，我们会收集长辈姓名、联系电话、地址、社区、紧急联系人，以及您主动填写的健康备注（如高血压、行动不便）。健康备注属于敏感个人信息，仅用于服务安排与安全提醒，不用于诊断或治疗。</p>
      <h2 class="section-title mt16">怎么使用</h2>
      <p>用于下单、派单、服务记录、回访和家属查看；不会向无关第三方提供。服务记录中的照片仅用于服务留痕和纠纷处理。</p>
      <h2 class="section-title mt16">授权与撤回</h2>
      <p>首次建档时需勾选授权；您可以随时联系管家撤回授权、删除档案。撤回后我们将停止使用，但已发生的服务记录按法规保留。</p>
      <h2 class="section-title mt16">数据安全</h2>
      <p>演示版数据存储在测试环境；正式上线将使用境内服务器、访问控制、加密传输与最小化收集。</p>
      <h2 class="section-title mt16">重要边界</h2>
      <p>本服务不提供医疗诊断、治疗、代问诊；陪诊仅做流程协助与记录。紧急情况请直接拨打 120。</p>
    </section>
  </main>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'
const router = useRouter()
</script>

<style scoped>
.page-intro { margin: 0 2px 14px; }
.page-intro h1 { margin: 6px 0 0; font-size: 26px; }
.page-intro p { margin: 4px 0 0; font-size: 10px; color: var(--muted); }
.card p { margin: 7px 0 0; font-size: 12px; line-height: 1.9; color: var(--sub); }
</style>
