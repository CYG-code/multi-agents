// 房间 Store（P2 阶段填充 WebSocket 相关状态）
import { defineStore } from 'pinia'

export const useRoomStore = defineStore('room', {
  state: () => ({
    currentRoom: null,
  }),
})
