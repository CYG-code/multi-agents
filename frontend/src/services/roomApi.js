import api from './api.js'

export const roomApi = {
  getMessages(roomId, params = {}) {
    return api.get(`/rooms/${roomId}/messages`, { params })
  },
  getTaskScriptState(roomId) {
    return api.get(`/rooms/${roomId}/task-script`)
  },
  requestFacilitatorProposal(roomId) {
    return api.post(`/rooms/${roomId}/task-script/proposals/facilitator`)
  },
  confirmTaskScriptProposal(roomId, payload = {}) {
    return api.post(`/rooms/${roomId}/task-script/confirm`, payload)
  },
}
