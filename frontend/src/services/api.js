import axios from 'axios'
import router from '../router/index.js'
import { useAuthStore } from '../stores/auth.js'

const api = axios.create({ baseURL: '/api' })
let sessionRevokedHandled = false

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

api.interceptors.response.use(
  (response) => response.data,
  (error) => {
    if (error.response?.status === 401) {
      const code = error.response?.data?.detail?.code
      if (code === 'SESSION_REVOKED' && !sessionRevokedHandled) {
        sessionRevokedHandled = true
        try {
          const authStore = useAuthStore()
          authStore.handleSessionRevoked('你的账号已在其他设备登录，当前会话已失效')
        } catch {
          localStorage.removeItem('token')
          localStorage.removeItem('user')
          window.alert('你的账号已在其他设备登录，当前会话已失效')
        }
      } else {
        localStorage.removeItem('token')
        localStorage.removeItem('user')
      }
      router.push('/login')
    }
    return Promise.reject(error)
  }
)

export default api
