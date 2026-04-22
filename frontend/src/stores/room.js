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
  }),

  actions: {
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
        this.currentTask = null

        if (room?.task_id) {
          this.currentTask = await api.get(`/tasks/${room.task_id}`)
        }
      } catch (error) {
        this.contextError = error.response?.data?.detail || '加载房间上下文失败'
        this.currentRoom = null
        this.currentTask = null
        this.taskScriptState = null
      } finally {
        this.loadingContext = false
      }

      // 下方面板独立加载，避免牵连上方“任务要求”窗口。
      this.loadTaskScriptState(roomId)
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
        }
      } catch (error) {
        this.taskSaveError = error.response?.data?.detail || error.message || '保存任务失败'
        throw error
      } finally {
        this.savingTask = false
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

    async requestFacilitatorTaskScriptProposal() {
      if (!this.currentRoomId) return
      this.requestingTaskScriptProposal = true
      this.taskScriptError = ''
      try {
        const nextState = await roomApi.requestFacilitatorProposal(this.currentRoomId)
        this.taskScriptState = nextState
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
      } catch (error) {
        this.taskScriptError = error.response?.data?.detail || '确认流程提案失败'
        throw error
      } finally {
        this.confirmingTaskScriptProposal = false
      }
    },
  },
})
