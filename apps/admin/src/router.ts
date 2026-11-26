import { createRouter, createWebHistory } from 'vue-router'
import AdminLayout from './layout/AdminLayout.vue'
import Login from './views/Login.vue'
import Dashboard from './views/Dashboard.vue'
import DispatchWorkbench from './views/DispatchWorkbench.vue'
import Anomalies from './views/Anomalies.vue'
import Orders from './views/Orders.vue'
import Elders from './views/Elders.vue'
import Services from './views/Services.vue'
import Staff from './views/Staff.vue'
import Suppliers from './views/Suppliers.vue'
import Reviews from './views/Reviews.vue'
import Stations from './views/Stations.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', component: Login, meta: { public: true } },
    {
      path: '/',
      component: AdminLayout,
      children: [
        { path: '', component: Dashboard },
        { path: 'dispatch', component: DispatchWorkbench },
        { path: 'anomalies', component: Anomalies },
        { path: 'orders', component: Orders },
        { path: 'elders', component: Elders },
        { path: 'services', component: Services },
        { path: 'staff', component: Staff },
        { path: 'stations', component: Stations },
        { path: 'suppliers', component: Suppliers },
        { path: 'reviews', component: Reviews }
      ]
    }
  ]
})

router.beforeEach((to) => {
  const token = localStorage.getItem('token')
  if (!to.meta.public && !token) return '/login'
  if (to.path === '/login' && token) return '/'
  return true
})

export default router
