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
  startRoomTimer(roomId) {
    return api.post(`/rooms/${roomId}/timer/start`)
  },
  resetRoomTimer(roomId) {
    return api.post(`/rooms/${roomId}/timer/reset`)
  },
  reportRoomActivity(roomId, activityType = 'writing') {
    return api.post(`/rooms/${roomId}/activity`, { activity_type: activityType })
  },
  getWritingSubmitState(roomId) {
    return api.get(`/rooms/${roomId}/writing-submit`)
  },
  confirmWritingSubmit(roomId) {
    return api.post(`/rooms/${roomId}/writing-submit/confirm`)
  },
  getWritingDocState(roomId) {
    return api.get(`/rooms/${roomId}/writing-doc`)
  },
  getWritingDocChangeLog(roomId, params = {}) {
    return api.get(`/rooms/${roomId}/writing-doc/change-log`, { params })
  },
  saveWritingDocVersion(roomId) {
    return api.post(`/rooms/${roomId}/writing-doc/save-version`)
  },
}
