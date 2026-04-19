import { defineStore } from 'pinia'
import api from '../services/api.js'

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
      } finally {
        this.loadingContext = false
      }
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
            title: `${this.currentRoom.name} - 任务`,
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
      } catch (error) {
        this.taskSaveError = error.response?.data?.detail || error.message || '保存任务失败'
        throw error
      } finally {
        this.savingTask = false
      }
    },
  },
})
