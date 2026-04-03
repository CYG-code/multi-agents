import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth.js'

const routes = [
  { path: '/', redirect: '/lobby' },
  { path: '/login', component: () => import('../views/LoginView.vue') },
  {
    path: '/lobby',
    component: () => import('../views/LobbyView.vue'),
    meta: { requiresAuth: true },
  },
  {
    path: '/room/:id',
    component: () => import('../views/RoomView.vue'),
    meta: { requiresAuth: true },
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to) => {
  const authStore = useAuthStore()
  if (to.meta.requiresAuth && !authStore.isAuthenticated) {
    return '/login'
  }
  if (to.meta.requiresTeacher && !authStore.isTeacher) {
    return '/lobby'
  }
})

export default router
