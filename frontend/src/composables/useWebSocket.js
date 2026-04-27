import { computed, onUnmounted, ref } from 'vue'
import ReconnectingWebSocket from 'reconnecting-websocket'
import { useAuthStore } from '../stores/auth.js'

const roomConnections = new Map()

function ensureRoomConnection(roomId, token) {
  const key = String(roomId || '')
  if (!key) return null

  if (roomConnections.has(key)) {
    return roomConnections.get(key)
  }

  const connected = ref(false)
  const handlers = new Map()

  const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
  const wsUrl = `${protocol}://${window.location.host}/ws/${key}`
  const ws = new ReconnectingWebSocket(wsUrl, [], {
    maxRetries: 10,
    reconnectionDelayGrowFactor: 1.5,
  })

  const conn = {
    roomId: key,
    ws,
    connected,
    handlers,
    refCount: 0,
    lastSeqNum: null,
  }

  ws.onopen = () => {
    ws.send(
      JSON.stringify({
        type: 'auth',
        token,
      })
    )
    connected.value = true

    if (conn.lastSeqNum !== null) {
      const reconnectHandlers = handlers.get('__reconnect__') || new Set()
      reconnectHandlers.forEach((handler) => {
        try {
          handler(conn.lastSeqNum)
        } catch {
          // ignore handler errors
        }
      })
    }
  }

  ws.onclose = (event) => {
    connected.value = false
    if ([4001, 4002, 4003].includes(event.code) && ws) {
      ws._shouldReconnect = false
      ws.close()
    }
  }

  ws.onmessage = (event) => {
    const data = JSON.parse(event.data)
    if (data.seq_num != null) {
      conn.lastSeqNum = data.seq_num
    }
    const eventHandlers = handlers.get(data.type) || new Set()
    eventHandlers.forEach((handler) => {
      try {
        handler(data)
      } catch {
        // ignore handler errors
      }
    })
  }

  roomConnections.set(key, conn)
  return conn
}

function closeRoomConnectionIfUnused(conn) {
  if (!conn || conn.refCount > 0) return
  try {
    conn.ws?.close()
  } catch {
    // ignore close errors
  }
  roomConnections.delete(conn.roomId)
}

export function useWebSocket(roomId) {
  const authStore = useAuthStore()
  const key = String(roomId || '')
  const connRef = ref(null)
  const registeredHandlers = []

  function connect() {
    if (!key) return
    const conn = ensureRoomConnection(key, authStore.token)
    if (!conn) return
    if (!connRef.value) {
      conn.refCount += 1
      connRef.value = conn
    }
  }

  function on(eventType, handler) {
    if (!connRef.value) connect()
    const conn = connRef.value
    if (!conn) return () => {}

    if (!conn.handlers.has(eventType)) {
      conn.handlers.set(eventType, new Set())
    }
    const set = conn.handlers.get(eventType)
    set.add(handler)
    registeredHandlers.push({ eventType, handler })

    return () => {
      const idx = registeredHandlers.findIndex((it) => it.eventType === eventType && it.handler === handler)
      if (idx >= 0) registeredHandlers.splice(idx, 1)
      set.delete(handler)
      if (set.size === 0) {
        conn.handlers.delete(eventType)
      }
    }
  }

  function send(data) {
    const conn = connRef.value
    if (conn?.connected?.value && conn.ws) {
      conn.ws.send(JSON.stringify(data))
    }
  }

  function disconnect() {
    const conn = connRef.value
    if (!conn) return

    registeredHandlers.splice(0).forEach(({ eventType, handler }) => {
      const set = conn.handlers.get(eventType)
      if (!set) return
      set.delete(handler)
      if (set.size === 0) {
        conn.handlers.delete(eventType)
      }
    })

    connRef.value = null
    conn.refCount = Math.max(0, conn.refCount - 1)
    closeRoomConnectionIfUnused(conn)
  }

  onUnmounted(disconnect)

  return {
    connect,
    on,
    send,
    disconnect,
    connected: computed(() => !!connRef.value?.connected?.value),
  }
}
