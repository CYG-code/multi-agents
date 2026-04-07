import { defineStore } from 'pinia'

export const useAgentStore = defineStore('agent', {
  state: () => ({
    typingStatus: {
      facilitator: false,
      devil_advocate: false,
      summarizer: false,
      resource_finder: false,
      encourager: false,
    },
  }),

  actions: {
    setTyping(role, isTyping) {
      if (role in this.typingStatus) {
        this.typingStatus[role] = isTyping
      }
    },

    clearTyping() {
      Object.keys(this.typingStatus).forEach((key) => {
        this.typingStatus[key] = false
      })
    },
  },
})
