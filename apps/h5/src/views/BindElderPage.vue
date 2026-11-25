<template>
  <main class="page no-tab">
    <header class="topbar">
      <button class="back" @click="router.back()">‹</button>
      <span class="topbar-title">绑定已有长辈</span>
      <span class="topbar-space"></span>
    </header>
    <div class="page-intro">
      <span class="eyebrow">FAMILY</span>
      <h1>绑定已有长辈</h1>
      <p>如果长辈档案已由其他家属创建，让对方在「我的长辈」里复制邀请码发给你。</p>
    </div>

    <section class="card organic">
      <div class="field">
        <div class="label required">邀请码</div>
        <input v-model="code" class="input code-input" maxlength="12" placeholder="例如 DEMO01" @input="code = code.toUpperCase()" />
      </div>
      <button class="btn btn-primary btn-block mt16" :disabled="!code || loading" @click="submit">确认绑定</button>
    </section>

    <section class="card warm">
      <h2 class="section-title">演示邀请码</h2>
      <p class="small muted mt8">仅供体验：DEMO01 张爷爷 · DEMO02 李奶奶 · DEMO03 王爷爷。</p>
      <button class="btn btn-ghost btn-block mt12" @click="router.push('/elders/new')">没有码？先新增长辈</button>
    </section>
  </main>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { post } from '../api/http'
import { showToast } from '../stores/toast'

const router = useRouter()
const code = ref('')
const loading = ref(false)

async function submit() {
  loading.value = true
  try {
    await post('/bindings', { invite_code: code.value.trim(), relation: 'family' })
    showToast('绑定成功')
    setTimeout(() => router.back(), 300)
  } catch (e: any) {
    showToast(e.message || '绑定失败')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.page-intro { margin: 0 2px 14px; }
.page-intro h1 { margin: 6px 0 0; font-size: 26px; }
.page-intro p { margin: 4px 0 0; font-size: 11px; line-height: 1.7; color: var(--muted); }
.code-input { letter-spacing: 3px; text-transform: uppercase; font-weight: 700; }
</style>
