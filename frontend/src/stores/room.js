import { defineStore } from 'pinia'
import api from '../services/api.js'
import { roomApi } from '../services/roomApi.js'

export const useRoomStore = defineStore('room', {
  state: () => ({
    currentRoomId: null,
    currentRoom: null,
    currentTask: null,
    loadingContext: false,
    contextError: '',
    savingTask: false,
    taskSaveError: '',
    taskSaveSuccessAt: 0,

    taskScriptState: null,
    loadingTaskScript: false,
    taskScriptError: '',
    requestingTaskScriptProposal: false,
    confirmingTaskScriptProposal: false,

    taskScriptLockState: null,
    loadingTaskScriptLock: false,
    taskScriptLockError: '',
    taskScriptLockNotice: '',
    acquiringTaskScriptLock: false,
    renewingTaskScriptLock: false,
    releasingTaskScriptLock: false,
    ownTaskScriptLeaseId: '',
    timerStartedAt: null,
    timerDeadlineAt: null,
    startingRoomTimer: false,
    roomTimerError: '',
  }),

  getters: {
    hasPendingTaskScriptProposal: (state) => !!state.taskScriptState?.pending_proposal,
    isTaskScriptLocked: (state) => !!state.taskScriptLockState?.locked,
    isTaskScriptLockMine: (state) => !!state.taskScriptLockState?.is_mine && !!state.ownTaskScriptLeaseId,
  },

  actions: {
    syncTimerFromRoom(room) {
      this.timerStartedAt = room?.timer_started_at || null
      this.timerDeadlineAt = room?.timer_deadline_at || null
    },

    applyRoomTimerUpdate(payload = {}) {
      const payloadRoomId = String(payload.room_id || '')
      if (!payloadRoomId || payloadRoomId !== this.currentRoomId) return

      this.timerStartedAt = payload.timer_started_at || null
      this.timerDeadlineAt = payload.timer_deadline_at || null
      if (this.currentRoom) {
        this.currentRoom = {
          ...this.currentRoom,
          timer_started_at: this.timerStartedAt,
          timer_deadline_at: this.timerDeadlineAt,
        }
      }
    },

    async loadRoomContext(roomId, force = false) {
      if (!roomId) return

      if (!force && this.currentRoomId === roomId && this.currentRoom) {
        return
      }

      this.loadingContext = true
      this.contextError = ''
      this.currentRoomId = roomId
      try {
        const room = await api.get(`/rooms/${roomId}`)
        this.currentRoom = room
        this.syncTimerFromRoom(room)
        this.currentTask = null

        if (room?.task_id) {
          this.currentTask = await api.get(`/tasks/${room.task_id}`)
        }
      } catch (error) {
        this.contextError = error.response?.data?.detail || '加载房间上下文失败'
        this.currentRoom = null
        this.currentTask = null
        this.taskScriptState = null
        this.taskScriptLockState = null
        this.syncTimerFromRoom(null)
      } finally {
        this.loadingContext = false
      }

      await this.loadTaskScriptState(roomId)
      await this.loadTaskScriptLockState(roomId)
    },

    async updateCurrentTask(patch) {
      this.savingTask = true
      this.taskSaveError = ''
      this.taskSaveSuccessAt = 0
      try {
        if (this.currentTask?.id) {
          const nextTask = await api.patch(`/tasks/${this.currentTask.id}`, patch)
          this.currentTask = nextTask
        } else {
          if (!this.currentRoomId || !this.currentRoom) {
            throw new Error('当前房间信息不存在，无法绑定任务')
          }
          const createdTask = await api.post('/tasks', {
            title: '任务',
            requirements: patch.requirements ?? null,
            scripts: patch.scripts ?? null,
          })

          const updatedRoom = await api.patch(`/rooms/${this.currentRoomId}/task`, {
            task_id: createdTask.id,
          })
          this.currentRoom = updatedRoom
          this.currentTask = createdTask
        }

        this.taskSaveSuccessAt = Date.now()
        if (this.currentRoomId) {
          await this.loadTaskScriptState(this.currentRoomId)
          await this.loadTaskScriptLockState(this.currentRoomId)
        }
      } catch (error) {
        this.taskSaveError = error.response?.data?.detail || error.message || '保存任务失败'
        throw error
      } finally {
        this.savingTask = false
      }
    },

    async startOrResetRoomTimer(roomId = this.currentRoomId) {
      if (!roomId) return null
      this.startingRoomTimer = true
      this.roomTimerError = ''
      try {
        const room = await roomApi.startOrResetRoomTimer(roomId)
        if (String(room?.id || '') === this.currentRoomId) {
          this.currentRoom = room
          this.syncTimerFromRoom(room)
        }
        return room
      } catch (error) {
        this.roomTimerError = error.response?.data?.detail || error.message || '计时器操作失败'
        throw error
      } finally {
        this.startingRoomTimer = false
      }
    },

    async loadTaskScriptState(roomId) {
      if (!roomId) return
      this.loadingTaskScript = true
      this.taskScriptError = ''
      try {
        this.taskScriptState = await roomApi.getTaskScriptState(roomId)
      } catch (error) {
        this.taskScriptState = null
        this.taskScriptError = error.response?.data?.detail || '加载任务流程状态失败'
      } finally {
        this.loadingTaskScript = false
      }
    },

    async loadTaskScriptLockState(roomId = this.currentRoomId) {
      if (!roomId) return
      this.loadingTaskScriptLock = true
      this.taskScriptLockError = ''
      try {
        this.taskScriptLockState = await roomApi.getTaskScriptLockState(roomId)
        if (!this.taskScriptLockState?.locked || this.taskScriptLockState?.is_mine) {
          this.taskScriptLockNotice = ''
        }
      } catch (error) {
        this.taskScriptLockError = error.response?.data?.detail || '加载编辑锁状态失败'
      } finally {
        this.loadingTaskScriptLock = false
      }
    },

    async acquireTaskScriptLock() {
      if (!this.currentRoomId) return null
      this.acquiringTaskScriptLock = true
      this.taskScriptLockError = ''
      this.taskScriptLockNotice = ''
      try {
        const result = await roomApi.acquireTaskScriptLock(this.currentRoomId)
        this.taskScriptLockState = result.lock || null
        if (result.acquired && result.lease_id) {
          this.ownTaskScriptLeaseId = result.lease_id
          this.taskScriptLockNotice = ''
        }
        if (!result.acquired) {
          const ownerName = result?.lock?.owner_display_name || '其他同学'
          this.taskScriptLockNotice = `当前由 ${ownerName} 正在编辑，你的输入已保留，可稍后重试。`
        }
        return result
      } catch (error) {
        this.taskScriptLockError = error.response?.data?.detail || error.message || '获取编辑锁失败'
        return null
      } finally {
        this.acquiringTaskScriptLock = false
      }
    },

    async renewTaskScriptLock() {
      if (!this.currentRoomId || !this.ownTaskScriptLeaseId) return null
      this.renewingTaskScriptLock = true
      this.taskScriptLockError = ''
      try {
        const result = await roomApi.renewTaskScriptLock(this.currentRoomId, this.ownTaskScriptLeaseId)
        this.taskScriptLockState = result.lock || null
        this.taskScriptLockNotice = ''
        return result
      } catch (error) {
        this.ownTaskScriptLeaseId = ''
        this.taskScriptLockNotice = error.response?.data?.detail || '编辑锁已失效，请重新进入编辑'
        return null
      } finally {
        this.renewingTaskScriptLock = false
      }
    },

    async releaseTaskScriptLock() {
      if (!this.currentRoomId || !this.ownTaskScriptLeaseId) return null
      this.releasingTaskScriptLock = true
      this.taskScriptLockError = ''
      try {
        const result = await roomApi.releaseTaskScriptLock(this.currentRoomId, this.ownTaskScriptLeaseId)
        this.taskScriptLockState = result.lock || null
        this.ownTaskScriptLeaseId = ''
        this.taskScriptLockNotice = ''
        return result
      } catch (error) {
        this.taskScriptLockError = error.response?.data?.detail || '释放编辑锁失败'
        return null
      } finally {
        this.releasingTaskScriptLock = false
      }
    },

    async requestFacilitatorTaskScriptProposal() {
      if (!this.currentRoomId) return
      this.requestingTaskScriptProposal = true
      this.taskScriptError = ''
      try {
        const nextState = await roomApi.requestFacilitatorProposal(this.currentRoomId)
        this.taskScriptState = nextState
        this.ownTaskScriptLeaseId = ''
        this.taskScriptLockNotice = ''
        await this.loadTaskScriptLockState(this.currentRoomId)
      } catch (error) {
        this.taskScriptError = error.response?.data?.detail || '主持智能体提案生成失败'
        throw error
      } finally {
        this.requestingTaskScriptProposal = false
      }
    },

    async confirmTaskScriptProposal(payload = {}) {
      if (!this.currentRoomId) return
      this.confirmingTaskScriptProposal = true
      this.taskScriptError = ''
      try {
        const nextState = await roomApi.confirmTaskScriptProposal(this.currentRoomId, payload)
        this.taskScriptState = nextState
        this.ownTaskScriptLeaseId = ''
        this.taskScriptLockNotice = ''
        await this.loadTaskScriptLockState(this.currentRoomId)
      } catch (error) {
        this.taskScriptError = error.response?.data?.detail || '确认流程提案失败'
        throw error
      } finally {
        this.confirmingTaskScriptProposal = false
      }
    },
  },
})
