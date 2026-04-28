import { ref, onUnmounted } from 'vue'
import ReconnectingWebSocket from 'reconnecting-websocket'
import { useAuthStore } from '../stores/auth.js'
import router from '../router/index.js'

export function useWebSocket(roomId) {
  const authStore = useAuthStore()
  const ws = ref(null)
  const connected = ref(false)
  const messageHandlers = new Map()
  let lastSeqNum = null

  function connect() {
    if (!roomId) return

    const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const wsUrl = `${protocol}://${window.location.host}/ws/${roomId}`

    ws.value = new ReconnectingWebSocket(wsUrl, [], {
      maxRetries: 10,
      reconnectionDelayGrowFactor: 1.5,
    })

    ws.value.onopen = () => {
      ws.value.send(
        JSON.stringify({
          type: 'auth',
          token: authStore.token,
        })
      )
      connected.value = true

      if (lastSeqNum !== null) {
        const handler = messageHandlers.get('__reconnect__')
        if (handler) handler(lastSeqNum)
      }
    }

    ws.value.onclose = (event) => {
      connected.value = false
      if ([4001, 4002, 4003].includes(event.code) && ws.value) {
        ws.value._shouldReconnect = false
        ws.value.close()
      }
    }

    ws.value.onmessage = (event) => {
      const data = JSON.parse(event.data)
      if (data?.type === 'auth:session_revoked') {
        authStore.handleSessionRevoked(data?.message || '你的账号已在其他设备登录，当前会话已失效')
        if (ws.value) {
          ws.value._shouldReconnect = false
          try {
            ws.value.close(4001, 'session revoked')
          } catch {
            // ignore close errors
          }
        }
        router.push('/login')
        return
      }
      if (data.seq_num != null) {
        lastSeqNum = data.seq_num
      }
      const handler = messageHandlers.get(data.type)
      if (handler) handler(data)
    }
  }

  function on(eventType, handler) {
    messageHandlers.set(eventType, handler)
  }

  function send(data) {
    if (connected.value && ws.value) {
      ws.value.send(JSON.stringify(data))
    }
  }

  function disconnect() {
    ws.value?.close()
  }

  onUnmounted(disconnect)

  return { connect, on, send, disconnect, connected }
}

