<template>
  <div class="app-shell">
    <router-view />
    <nav v-if="showTab" class="tabbar">
      <router-link
        v-for="tab in tabs"
        :key="tab.path"
        :to="tab.path"
        class="tab-item"
        :class="{ active: isActive(tab.path) }"
      >
        <img :src="isActive(tab.path) ? tab.activeIcon : tab.icon" alt="" />
        <span>{{ tab.label }}</span>
      </router-link>
    </nav>
    <transition name="toast">
      <div v-if="toast.visible" class="toast">{{ toast.text }}</div>
    </transition>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { auth } from './stores/auth'
import { useRoute } from 'vue-router'
import { toast } from './stores/toast'
import homeIcon from './assets/tabbar/home.png'
import homeActive from './assets/tabbar/home-active.png'
import orderIcon from './assets/tabbar/orders.png'
import orderActive from './assets/tabbar/orders-active.png'
import profileIcon from './assets/tabbar/profile.png'
import profileActive from './assets/tabbar/profile-active.png'

const route = useRoute()
const isStaff = computed(() => auth.user?.role === 'staff')
const customerTabs = [
  { path: '/', label: '首页', icon: homeIcon, activeIcon: homeActive },
  { path: '/orders', label: '订单', icon: orderIcon, activeIcon: orderActive },
  { path: '/profile', label: '我的', icon: profileIcon, activeIcon: profileActive }
]
const staffTabs = [
  { path: '/staff/orders', label: '工作台', icon: homeIcon, activeIcon: homeActive },
  { path: '/staff/profile', label: '我的', icon: profileIcon, activeIcon: profileActive }
]
const tabs = computed(() => isStaff.value ? staffTabs : customerTabs)
const showTab = computed(() => {
  if (isStaff.value) return ['/staff/orders', '/staff/profile'].includes(route.path)
  return !!route.meta.tab
})

function isActive(path: string) {
  if (isStaff.value) {
    if (path === '/staff/profile') return route.path.startsWith('/staff/profile')
    return route.path.startsWith('/staff/orders')
  }
  return path === '/' ? route.path === '/' : route.path.startsWith(path)
}
</script>
