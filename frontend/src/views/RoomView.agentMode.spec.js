import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { reactive } from 'vue'

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
  default: { name: 'WritingArea', template: '<div data-test="writing-area">Writing</div>' },
}))

vi.mock('../components/chat/ChatPanel.vue', () => ({
  default: { name: 'ChatPanel', template: '<div data-test="chat-panel">Chat</div>' },
}))

vi.mock('../components/task/TaskRequirements.vue', () => ({
  default: { name: 'TaskRequirements', template: '<div data-test="task-requirements">TaskRequirements</div>' },
}))

vi.mock('../components/task/TaskScript.vue', () => ({
  default: { name: 'TaskScript', template: '<div data-test="task-script">TaskScript</div>' },
}))

import RoomView from './RoomView.vue'

function mountRoomView() {
  return mount(RoomView)
}

describe('RoomView task flow panel by agent_mode', () => {
  beforeEach(() => {
    mockedRoom = reactive({ id: 'room-1', agent_mode: 'multi' })
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('renders_task_flow_panel_in_multi_mode', () => {
    mockedRoom.agent_mode = 'multi'
    const wrapper = mountRoomView()
    expect(wrapper.find('[data-test="task-script"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="writing-area"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="chat-panel"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="task-requirements"]').exists()).toBe(true)
  })

  it('hides_task_flow_panel_in_none_mode', () => {
    mockedRoom.agent_mode = 'none'
    const wrapper = mountRoomView()
    expect(wrapper.find('[data-test="task-script"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="writing-area"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="chat-panel"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="task-requirements"]').exists()).toBe(true)
  })

  it('hides_task_flow_panel_in_single_mode', () => {
    mockedRoom.agent_mode = 'single'
    const wrapper = mountRoomView()
    expect(wrapper.find('[data-test="task-script"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="writing-area"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="chat-panel"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="task-requirements"]').exists()).toBe(true)
  })
})
