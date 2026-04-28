import { ref } from 'vue'
import ReconnectingWebSocket from 'reconnecting-websocket'
import { useAuthStore } from '../stores/auth.js'
import router from '../router/index.js'

const roomConnections = new Map()

function getOrCreateConnection(roomId) {
  let state = roomConnections.get(roomId)
  if (state) return state

  state = {
    ws: null,
    connected: ref(false),
    handlers: new Map(),
    lastSeqNum: null,
    refCount: 0,
    shouldReconnect: true,
  }
  roomConnections.set(roomId, state)
  return state
}

function emit(state, eventType, payload) {
  const listeners = state.handlers.get(eventType)
  if (!listeners || listeners.size === 0) return
  for (const listener of Array.from(listeners)) {
    try {
      listener(payload)
    } catch {
      // Ignore consumer exceptions to keep the socket loop healthy.
    }
  }
}

function createSocket(roomId, state, authStore) {
  const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
  const wsUrl = `${protocol}://${window.location.host}/ws/${roomId}`

  const socket = new ReconnectingWebSocket(wsUrl, [], {
    maxRetries: 20,
    reconnectionDelayGrowFactor: 1.5,
    connectionTimeout: 10000,
  })
  state.ws = socket
  state.shouldReconnect = true

  socket.onopen = () => {
    const token = authStore.token
    if (!token) {
      try {
        socket.close(4001, 'missing token')
      } catch {
        // ignore close errors
      }
      return
    }

    socket.send(
      JSON.stringify({
        type: 'auth',
        token,
      })
    )
    state.connected.value = true

    if (state.lastSeqNum !== null) {
      emit(state, '__reconnect__', state.lastSeqNum)
    }
  }

  socket.onclose = (event) => {
    state.connected.value = false
    if ([4001, 4002, 4003].includes(event.code)) {
      state.shouldReconnect = false
      socket._shouldReconnect = false
    }
  }

  socket.onmessage = (event) => {
    let data
    try {
      data = JSON.parse(event.data)
    } catch {
      return
    }

    if (data?.type === 'auth:session_revoked') {
      authStore.handleSessionRevoked(data?.message || '你的账号已在其他设备登录，当前会话已失效')
      state.shouldReconnect = false
      socket._shouldReconnect = false
      try {
        socket.close(4001, 'session revoked')
      } catch {
        // ignore close errors
      }
      router.push('/login')
      return
    }

    if (data?.seq_num != null) {
      state.lastSeqNum = data.seq_num
    }
    emit(state, data?.type, data)
  }
}

function maybeCloseConnection(roomId, state) {
  if (state.refCount > 0) return
  const socket = state.ws
  state.connected.value = false
  state.handlers.clear()
  state.lastSeqNum = null
  state.shouldReconnect = false
  if (socket) {
    socket._shouldReconnect = false
    try {
      socket.close()
    } catch {
      // ignore close errors
    }
  }
  state.ws = null
  roomConnections.delete(roomId)
}

export function useWebSocket(roomId) {
  const authStore = useAuthStore()
  const localSubs = []
  const consumerId = Symbol(`ws-consumer:${roomId}`)
  const state = roomId ? getOrCreateConnection(roomId) : null
  let connectedByConsumer = false

  function connect() {
    if (!roomId || !state) return
    if (!connectedByConsumer) {
      state.refCount += 1
      connectedByConsumer = true
    }
    if (!state.ws) {
      createSocket(roomId, state, authStore)
    }
  }

  function on(eventType, handler) {
    if (!state) return () => {}
    if (!state.handlers.has(eventType)) {
      state.handlers.set(eventType, new Map())
    }
    state.handlers.get(eventType).set(consumerId, handler)
    const unsubscribe = () => {
      const listeners = state.handlers.get(eventType)
      if (!listeners) return
      listeners.delete(consumerId)
      if (listeners.size === 0) {
        state.handlers.delete(eventType)
      }
    }
    localSubs.push(unsubscribe)
    return unsubscribe
  }

  function send(data) {
    if (!state?.ws || !state.connected.value) return
    try {
      state.ws.send(JSON.stringify(data))
    } catch {
      // ignore send errors on unstable sockets
    }
  }

  function disconnect() {
    if (!state) return
    while (localSubs.length > 0) {
      const unsub = localSubs.pop()
      try {
        unsub()
      } catch {
        // ignore unsubscribe failures
      }
    }
    if (connectedByConsumer) {
      connectedByConsumer = false
      state.refCount = Math.max(0, state.refCount - 1)
    }
    maybeCloseConnection(roomId, state)
  }

  return {
    connect,
    on,
    send,
    disconnect,
    connected: state ? state.connected : ref(false),
  }
}
