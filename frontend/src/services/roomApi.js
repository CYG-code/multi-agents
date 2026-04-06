import api from './api.js'

export const roomApi = {
  getMessages(roomId, params = {}) {
    return api.get(`/rooms/${roomId}/messages`, { params })
  },
}
