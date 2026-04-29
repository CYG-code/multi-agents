import { describe, it, expect, beforeEach, vi } from 'vitest'

const wsState = vi.hoisted(() => ({ instances: [] }))

vi.mock('reconnecting-websocket', () => {
  class FakeReconnectingWebSocket {
    constructor(url) {
      this.url = url
      this.readyState = 0
      this.closeCount = 0
      this.listeners = new Map()
      this._shouldReconnect = true
      this.onopen = null
      this.onclose = null
      this.onerror = null
      this.onmessage = null
      wsState.instances.push(this)
    }

    addEventListener(type, handler) {
      if (!this.listeners.has(type)) this.listeners.set(type, [])
      this.listeners.get(type).push(handler)
    }

    send() {}

    close(code = 1000, reason = '') {
      this.closeCount += 1
      this.readyState = 3
      if (typeof this.onclose === 'function') {
        this.onclose({ code, reason, wasClean: true })
      }
    }
  }

  return { default: FakeReconnectingWebSocket }
})

vi.mock('../stores/auth.js', () => ({
  useAuthStore: () => ({ token: 'test-token', handleSessionRevoked: vi.fn() }),
}))

vi.mock('../router/index.js', () => ({
  default: { push: vi.fn() },
}))

let useWebSocket
let mount
let defineComponent
let ref
let nextTick
let onMounted

beforeEach(async () => {
  wsState.instances.length = 0
  vi.clearAllMocks()
  vi.resetModules()

  const vue = await import('vue')
  defineComponent = vue.defineComponent
  ref = vue.ref
  nextTick = vue.nextTick
  onMounted = vue.onMounted

  const testUtils = await import('@vue/test-utils')
  mount = testUtils.mount

  ;({ useWebSocket } = await import('./useWebSocket.js'))
})

function makeChild() {
  return defineComponent({
    name: 'WsChild',
    props: {
      roomId: { type: String, required: true },
      tick: { type: Number, default: 0 },
    },
    setup(props, { expose }) {
      const { connect } = useWebSocket(props.roomId)
      const counter = ref(0)
      onMounted(() => connect())
      const bump = () => {
        counter.value += 1
      }
      expose({ bump })
      return { counter }
    },
    template: '<div>{{ counter }} {{ tick }}</div>',
  })
}

describe('useWebSocket lifecycle', () => {
  it('A. same room should create only one websocket', async () => {
    const Child = makeChild()
    const wrapper = mount(Child, { props: { roomId: 'room-a', tick: 0 } })

    await nextTick()
    await wrapper.setProps({ roomId: 'room-a', tick: 1 })
    await wrapper.setProps({ roomId: 'room-a', tick: 2 })

    expect(wsState.instances.length).toBe(1)
  })

  it('B. should not cleanup before open during normal mount', async () => {
    const Child = makeChild()
    mount(Child, { props: { roomId: 'room-a' } })

    await nextTick()
    expect(wsState.instances.length).toBe(1)
    expect(wsState.instances[0].closeCount).toBe(0)
  })

  it('C. should close exactly once on component unmount', async () => {
    const Child = makeChild()
    const wrapper = mount(Child, { props: { roomId: 'room-a' } })

    await nextTick()
    wrapper.unmount()

    expect(wsState.instances[0].closeCount).toBe(1)
  })

  it('D. should recreate websocket only when roomId changes', async () => {
    const Child = makeChild()

    const Parent = defineComponent({
      components: { Child },
      setup() {
        const roomId = ref('room-a')
        return { roomId }
      },
      template: '<Child :key="roomId" :room-id="roomId" />',
    })

    const wrapper = mount(Parent)
    await nextTick()

    const first = wsState.instances[0]
    wrapper.vm.roomId = 'room-b'
    await nextTick()

    expect(wsState.instances.length).toBe(2)
    expect(first.closeCount).toBe(1)
    expect(wsState.instances[1].url).toContain('/ws/room-b')
  })

  it('E. repeated renders should not create multiple websocket instances', async () => {
    const Child = makeChild()

    const Parent = defineComponent({
      components: { Child },
      setup() {
        const tick = ref(0)
        return { tick }
      },
      template: '<Child room-id="room-a" :tick="tick" />',
    })

    const wrapper = mount(Parent)
    await nextTick()

    wrapper.vm.tick += 1
    await nextTick()
    wrapper.vm.tick += 1
    await nextTick()
    wrapper.vm.tick += 1
    await nextTick()

    expect(wsState.instances.length).toBe(1)
  })
})
