import { createRouter, createWebHistory } from 'vue-router'
import { auth } from './stores/auth'
import LoginPage from './views/LoginPage.vue'
import HomePage from './views/HomePage.vue'
import OrdersPage from './views/OrdersPage.vue'
import OrderDetailPage from './views/OrderDetailPage.vue'
import CreateOrderPage from './views/CreateOrderPage.vue'
import EldersPage from './views/EldersPage.vue'
import ElderEditPage from './views/ElderEditPage.vue'
import BindElderPage from './views/BindElderPage.vue'
import ProfilePage from './views/ProfilePage.vue'
import PrivacyPage from './views/PrivacyPage.vue'
import EmergencyPage from './views/EmergencyPage.vue'
import StaffOrdersPage from './views/StaffOrdersPage.vue'
import StaffProfilePage from './views/StaffProfilePage.vue'
import StaffEldersPage from './views/StaffEldersPage.vue'
import StaffRecordPage from './views/StaffRecordPage.vue'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  scrollBehavior: () => ({ top: 0 }),
  routes: [
    { path: '/login', component: LoginPage, meta: { public: true } },
    { path: '/', component: HomePage, meta: { tab: 'home' } },
    { path: '/orders', component: OrdersPage, meta: { tab: 'orders' } },
    { path: '/orders/:id', component: OrderDetailPage },
    { path: '/create', component: CreateOrderPage },
    { path: '/elders', component: EldersPage },
    { path: '/elders/new', component: ElderEditPage },
    { path: '/elders/:id/edit', component: ElderEditPage },
    { path: '/elders/bind', component: BindElderPage },
    { path: '/profile', component: ProfilePage, meta: { tab: 'profile' } },
    { path: '/privacy', component: PrivacyPage },
    { path: '/emergency', component: EmergencyPage },
    { path: '/staff/home', redirect: '/staff/orders' },
    { path: '/staff/orders', component: StaffOrdersPage },
    { path: '/staff/profile', component: StaffProfilePage },
    { path: '/staff/elders', component: StaffEldersPage },
    { path: '/staff/record/:id', component: StaffRecordPage },
    { path: '/:pathMatch(.*)*', redirect: '/' }
  ]
})

router.beforeEach((to) => {
  if (to.meta.public) {
    if (to.path === '/login' && auth.token) {
      return auth.user?.role === 'staff' ? '/staff/orders' : '/'
    }
    return true
  }
  if (!auth.token) return '/login'
  if (auth.user?.role === 'staff' && !to.path.startsWith('/staff') && to.path !== '/privacy') return '/staff/orders'
  if (auth.user?.role !== 'staff' && to.path.startsWith('/staff')) return '/'
  return true
})

export default router
