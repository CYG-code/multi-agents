import { defineStore } from 'pinia'
import { roomApi } from '../services/roomApi.js'

export const useChatStore = defineStore('chat', {
  state: () => ({
    messages: [],
    hasMore: true,
    oldestSeq: null,
    loading: false,
  }),

  actions: {
    async loadHistory(roomId) {
      this.loading = true
      try {
        const result = await roomApi.getMessages(roomId)
        this.messages = result.messages || []
        this.hasMore = result.has_more ?? false
        this.oldestSeq = result.oldest_seq ?? null
      } finally {
        this.loading = false
      }
    },

    async loadMore(roomId) {
      if (!this.hasMore || this.loading) return
      this.loading = true
      try {
        const result = await roomApi.getMessages(roomId, {
          before_seq: this.oldestSeq,
        })
        this.messages = [...(result.messages || []), ...this.messages]
        this.hasMore = result.has_more ?? false
        this.oldestSeq = result.oldest_seq ?? this.oldestSeq
      } finally {
        this.loading = false
      }
    },

    addMessage(message) {
      if (!this.messages.find((m) => m.id === message.id)) {
        this.messages.push(message)
      }
    },

    clearMessages() {
      this.messages = []
      this.hasMore = true
      this.oldestSeq = null
      this.loading = false
    },
  },
})

