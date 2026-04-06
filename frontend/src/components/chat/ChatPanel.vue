<template>
  <div class="flex flex-col h-full border border-gray-200 bg-white">
    <div class="p-3 border-b border-gray-100 flex items-center justify-between">
      <p class="text-xs font-semibold text-gray-400 uppercase tracking-wide">实时聊天室</p>
      <span class="text-xs text-gray-500">在线 {{ onlineCount }}</span>
    </div>

    <div v-if="!connected" class="bg-yellow-100 text-yellow-700 text-xs text-center py-1">
      正在连接聊天室...
    </div>

    <MessageList
      ref="messageListRef"
      :messages="chatStore.messages"
      :has-more="chatStore.hasMore"
      class="flex-1"
      @load-more="handleLoadMore"
      @viewport-change="handleViewportChange"
    />

    <div v-if="unreadCount > 0" class="px-3 pb-2">
      <button
        class="w-full py-2 text-xs rounded-lg bg-blue-50 text-blue-600 border border-blue-100 hover:bg-blue-100 transition-colors"
        @click="scrollToLatest"
      >
        有 {{ unreadCount }} 条新消息，点击查看最新
      </button>
    </div>

    <ChatInput class="flex-shrink-0" @send="handleSendMessage" />
  </div>
</template>

<script setup>
import { nextTick, onMounted, onUnmounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import ChatInput from './ChatInput.vue'
import MessageList from './MessageList.vue'
import { useWebSocket } from '../../composables/useWebSocket.js'
import { useAuthStore } from '../../stores/auth.js'
import { useChatStore } from '../../stores/chat.js'

const route = useRoute()
const authStore = useAuthStore()
const roomId = String(route.params.id || '')
const chatStore = useChatStore()
const messageListRef = ref(null)
const onlineCount = ref(0)
const unreadCount = ref(0)
const isAtBottom = ref(true)

const { connect, on, send, disconnect, connected } = useWebSocket(roomId)

function scrollToBottom() {
  messageListRef.value?.scrollToBottom()
}

async function scrollToLatest() {
  unreadCount.value = 0
  await nextTick()
  scrollToBottom()
}

function handleViewportChange(payload) {
  isAtBottom.value = !!payload?.atBottom
  if (isAtBottom.value) {
    unreadCount.value = 0
  }
}

async function reloadHistory() {
  if (!roomId) return
  await chatStore.loadHistory(roomId)
  await nextTick()
  scrollToBottom()
}

async function handleLoadMore() {
  await chatStore.loadMore(roomId)
}

function handleSendMessage(content, mentions = []) {
  send({
    type: 'chat:message',
    content,
    mentions,
  })
}

onMounted(async () => {
  if (!roomId) return

  await reloadHistory()

  on('chat:new_message', async (data) => {
    const isSelfMessage = !!data.sender_id && data.sender_id === authStore.user?.id
    chatStore.addMessage(data)
    await nextTick()

    if (isSelfMessage || isAtBottom.value) {
      scrollToBottom()
      unreadCount.value = 0
      return
    }

    unreadCount.value += 1
  })

  on('room:user_join', (data) => {
    if (typeof data.online_count === 'number') {
      onlineCount.value = data.online_count
    }
  })

  on('room:user_leave', (data) => {
    if (typeof data.online_count === 'number') {
      onlineCount.value = data.online_count
    }
  })

  // Re-sync history after reconnect to avoid message gaps.
  on('__reconnect__', async () => {
    unreadCount.value = 0
    await reloadHistory()
  })

  connect()
})

onUnmounted(() => {
  disconnect()
  chatStore.clearMessages()
})
</script>
