import { defineStore } from 'pinia'
import api from '../services/api.js'

let sessionRevokedHandled = false

export const useAuthStore = defineStore('auth', {
  state: () => ({
    user: JSON.parse(localStorage.getItem('user')) || null,
    token: localStorage.getItem('token') || null,
  }),
  getters: {
    isAuthenticated: (state) => !!state.token,
    isTeacher: (state) => state.user?.role === 'teacher',
  },
  actions: {
    async login(username, password) {
      const data = await api.post('/auth/login', { username, password })
      sessionRevokedHandled = false
      this.token = data.access_token
      this.user = data.user
      localStorage.setItem('token', data.access_token)
      localStorage.setItem('user', JSON.stringify(data.user))
    },
    async register(payload) {
      const data = await api.post('/auth/register', payload)
      sessionRevokedHandled = false
      this.token = data.access_token
      this.user = data.user
      localStorage.setItem('token', data.access_token)
      localStorage.setItem('user', JSON.stringify(data.user))
    },
    logout() {
      this.user = null
      this.token = null
      localStorage.removeItem('token')
      localStorage.removeItem('user')
    },
    handleSessionRevoked(message = '你的账号已在其他设备登录，当前会话已失效') {
      if (sessionRevokedHandled) return
      sessionRevokedHandled = true
      this.logout()
      window.alert(message)
    },
    resetSessionRevokedFlag() {
      sessionRevokedHandled = false
    },
  },
})
