import api from './api.js'

export const roomApi = {
  getMessages(roomId, params = {}) {
    return api.get(`/rooms/${roomId}/messages`, { params })
  },
  getTaskScriptState(roomId) {
    return api.get(`/rooms/${roomId}/task-script`)
  },
  getTaskScriptLockState(roomId) {
    return api.get(`/rooms/${roomId}/task-script/lock`)
  },
  acquireTaskScriptLock(roomId) {
    return api.post(`/rooms/${roomId}/task-script/lock/acquire`)
  },
  renewTaskScriptLock(roomId, leaseId) {
    return api.post(`/rooms/${roomId}/task-script/lock/renew`, { lease_id: leaseId })
  },
  releaseTaskScriptLock(roomId, leaseId) {
    return api.post(`/rooms/${roomId}/task-script/lock/release`, { lease_id: leaseId })
  },
  requestFacilitatorProposal(roomId) {
    return api.post(`/rooms/${roomId}/task-script/proposals/facilitator`)
  },
  confirmTaskScriptProposal(roomId, payload = {}) {
    return api.post(`/rooms/${roomId}/task-script/confirm`, payload)
  },
  startOrResetRoomTimer(roomId) {
    return api.post(`/rooms/${roomId}/timer/start`)
  },
}
