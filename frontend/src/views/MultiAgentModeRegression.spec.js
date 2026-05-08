import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { reactive } from 'vue'
import ChatInput from '../components/chat/ChatInput.vue'

let mockedRoom

vi.mock('../stores/auth.js', () => ({
  useAuthStore: () => ({
    isTeacher: false,
    user: { id: 'u1', role: 'student' },
  }),
}))

vi.mock('../stores/room.js', () => ({
  useRoomStore: () => ({
    currentRoomId: 'room-1',
    currentRoom: mockedRoom,
    currentTask: { id: 'task-1' },
    loadingContext: false,
    contextError: '',
    savingTask: false,
    taskSaveError: '',
    taskSaveSuccessAt: 0,
    taskScriptState: {},
    loadingTaskScript: false,
    taskScriptError: '',
    taskScriptLockNotice: '',
    taskScriptLockError: '',
    requestingTaskScriptProposal: false,
    confirmingTaskScriptProposal: false,
    taskScriptLockState: null,
    isTaskScriptLockMine: false,
    acquiringTaskScriptLock: false,
    releasingTaskScriptLock: false,
    ownTaskScriptLeaseId: '',
    timerStartedAt: null,
    timerDeadlineAt: null,
    timerStoppedAt: null,
    startingRoomTimer: false,
    loadRoomContext: vi.fn(),
    updateCurrentTask: vi.fn(),
    requestFacilitatorTaskScriptProposal: vi.fn(),
    acquireTaskScriptLock: vi.fn(),
    releaseTaskScriptLock: vi.fn(),
    confirmTaskScriptProposal: vi.fn(),
    renewTaskScriptLock: vi.fn(),
    startRoomTimer: vi.fn(),
    resetRoomTimer: vi.fn(),
    loadTaskScriptState: vi.fn(),
    loadTaskScriptLockState: vi.fn(),
    loadWritingSubmitState: vi.fn(),
    applyRoomTimerUpdate: vi.fn(),
    applyWritingSubmitUpdate: vi.fn(),
  }),
}))

vi.mock('vue-router', () => {
  const push = vi.fn()
  return {
    useRoute: () => ({ params: { id: 'room-1' } }),
    useRouter: () => ({ push }),
    createRouter: vi.fn(() => ({
      push,
      replace: vi.fn(),
      beforeEach: vi.fn(),
      afterEach: vi.fn(),
      isReady: vi.fn(async () => {}),
    })),
    createWebHistory: vi.fn(() => ({})),
  }
})

vi.mock('../components/layout/WritingArea.vue', () => ({
  default: { name: 'WritingArea', template: '<div data-test="writing-area">\u5199\u4f5c\u533a</div>' },
}))

vi.mock('../components/chat/ChatPanel.vue', () => ({
  default: { name: 'ChatPanel', template: '<div data-test="chat-panel">\u804a\u5929\u533a</div>' },
}))

vi.mock('../components/task/TaskRequirements.vue', () => ({
  default: { name: 'TaskRequirements', template: '<div data-test="task-requirements">\u4efb\u52a1\u8981\u6c42</div>' },
}))

vi.mock('../components/task/TaskScript.vue', () => ({
  default: {
    name: 'TaskScript',
    template: `
      <div data-test="task-script">
        <div>\u4efb\u52a1\u6d41\u7a0b</div>
        <div>\u8ba9\u4e3b\u6301\u667a\u80fd\u4f53\u66f4\u65b0\u5efa\u8bae</div>
        <div>\u5f53\u524d\u72b6\u6001</div>
        <div>\u4e0b\u4e00\u6b65\u76ee\u6807</div>
      </div>
    `,
  },
}))

import RoomView from './RoomView.vue'

describe('Multi-agent mode regression', () => {
  beforeEach(() => {
    mockedRoom = reactive({ id: 'room-1', agent_mode: 'multi' })
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('shows six multi-agent entries in ChatInput under multi mode', async () => {
    const wrapper = mount(ChatInput, {
      props: { agentMode: 'multi' },
    })

    await wrapper.find('button').trigger('click')
    const text = wrapper.text()

    expect(text).toContain('\u4e3b\u6301\u4eba')
    expect(text).toContain('\u6279\u5224\u8005')
    expect(text).toContain('\u603b\u7ed3\u8005')
    expect(text).toContain('\u8d44\u6e90\u68c0\u7d22\u8005')
    expect(text).toContain('\u9f13\u52b1\u8005')
    expect(text).toContain('\u6982\u5ff5\u89e3\u91ca\u5458')
    expect(text).not.toContain('\u82cf\u683c\u62c9\u5e95\u667a\u80fd\u4f53')
  })

  it('renders task flow and core areas in RoomView under multi mode', () => {
    mockedRoom.agent_mode = 'multi'
    const wrapper = mount(RoomView)
    const text = wrapper.text()

    expect(wrapper.find('[data-test="task-script"]').exists()).toBe(true)
    expect(text).toContain('\u4efb\u52a1\u6d41\u7a0b')
    expect(text).toContain('\u8ba9\u4e3b\u6301\u667a\u80fd\u4f53\u66f4\u65b0\u5efa\u8bae')
    expect(text).toContain('\u5f53\u524d\u72b6\u6001')
    expect(text).toContain('\u4e0b\u4e00\u6b65\u76ee\u6807')

    expect(wrapper.find('[data-test="writing-area"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="chat-panel"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="task-requirements"]').exists()).toBe(true)
    expect(text).toContain('\u804a\u5929\u533a')
    expect(text).toContain('\u5199\u4f5c\u533a')
    expect(text).toContain('\u4efb\u52a1\u8981\u6c42')
  })
})
