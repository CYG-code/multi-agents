<template>
  <div class="flex flex-col h-full border border-gray-200 bg-white">
    <div class="p-3 border-b border-gray-100 flex items-center justify-between">
      <p class="text-xs font-semibold text-gray-400 uppercase tracking-wide">Realtime Chat Room</p>
      <span class="text-xs text-gray-500">Online {{ onlineCount }}</span>
    </div>

    <div v-if="!connected" class="bg-yellow-100 text-yellow-700 text-xs text-center py-1">
      Reconnecting to chat server...
    </div>

    <MessageList
      ref="messageListRef"
      :messages="chatStore.messages"
      :has-more="chatStore.hasMore"
      class="flex-1"
      @load-more="handleLoadMore"
      @viewport-change="handleViewportChange"
    />

    <AgentTypingIndicator />

    <div v-if="invokeStatusList.length > 0" class="px-3 pb-2 space-y-1">
      <div
        v-for="item in invokeStatusList"
        :key="item.key"
        class="text-xs rounded-lg border px-2 py-1"
        :class="statusClass(item.status)"
      >
        {{ roleLabel(item.agent_role) }}：{{ statusText(item.status, item.message) }}
      </div>
    </div>

    <div v-if="unreadCount > 0" class="px-3 pb-2">
      <button
        class="w-full py-2 text-xs rounded-lg bg-blue-50 text-blue-600 border border-blue-100 hover:bg-blue-100 transition-colors"
        @click="scrollToLatest"
      >
        {{ unreadCount }} new messages, click to jump to latest
      </button>
    </div>

    <ChatInput class="flex-shrink-0" @send="handleSendMessage" />
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import ChatInput from './ChatInput.vue'
import MessageList from './MessageList.vue'
import AgentTypingIndicator from './AgentTypingIndicator.vue'
import { useAgentStream } from '../../composables/useAgentStream.js'
import { useWebSocket } from '../../composables/useWebSocket.js'
import { useAgentStore } from '../../stores/agent.js'
import { useAuthStore } from '../../stores/auth.js'
import { useChatStore } from '../../stores/chat.js'

const route = useRoute()
const authStore = useAuthStore()
const chatStore = useChatStore()
const agentStore = useAgentStore()
const roomId = String(route.params.id || '')

const messageListRef = ref(null)
const onlineCount = ref(0)
const unreadCount = ref(0)
const isAtBottom = ref(true)
const invokeStatusMap = ref(new Map())

const { connect, on, send, disconnect, connected } = useWebSocket(roomId)
const { handleTyping, handleStream, handleStreamEnd } = useAgentStream()

const ROLE_NAMES = {
  facilitator: '主持人',
  devil_advocate: '批判者',
  summarizer: '总结者',
  resource_finder: '资源检索者',
  encourager: '鼓励者',
}

const invokeStatusList = computed(() => {
  return Array.from(invokeStatusMap.value.values())
    .filter((item) => item.status !== 'completed')
    .sort((a, b) => b.updated_at - a.updated_at)
})

function roleLabel(role) {
  return ROLE_NAMES[role] || role
}

function statusText(status, message) {
  if (message) return message
  const map = {
    accepted: '已接收',
    queued: '排队中',
    thinking: '思考中',
    failed: '回复失败',
    unsupported: '当前版本暂不支持该智能体',
    completed: '回复完成',
  }
  return map[status] || status
}

function statusClass(status) {
  const map = {
    accepted: 'border-blue-200 bg-blue-50 text-blue-700',
    queued: 'border-sky-200 bg-sky-50 text-sky-700',
    thinking: 'border-indigo-200 bg-indigo-50 text-indigo-700',
    failed: 'border-red-200 bg-red-50 text-red-700',
    unsupported: 'border-amber-200 bg-amber-50 text-amber-700',
    completed: 'border-green-200 bg-green-50 text-green-700',
  }
  return map[status] || 'border-gray-200 bg-gray-50 text-gray-700'
}

function upsertInvokeStatus(payload) {
  if (!payload?.source_message_id || !payload?.agent_role) return
  const key = `${payload.source_message_id}:${payload.agent_role}`
  const next = new Map(invokeStatusMap.value)
  next.set(key, {
    key,
    source_message_id: payload.source_message_id,
    agent_role: payload.agent_role,
    status: payload.status || 'accepted',
    message: payload.message || '',
    updated_at: Date.now(),
  })
  invokeStatusMap.value = next
}

function removeInvokeStatus(key) {
  const next = new Map(invokeStatusMap.value)
  next.delete(key)
  invokeStatusMap.value = next
}

function setTemporaryStatus(payload, delayMs = 5000) {
  if (!payload?.source_message_id || !payload?.agent_role) return
  upsertInvokeStatus(payload)
  const key = `${payload.source_message_id}:${payload.agent_role}`
  setTimeout(() => removeInvokeStatus(key), delayMs)
}

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

  on('agent:ack', (data) => {
    upsertInvokeStatus(data)
    if (data?.status === 'unsupported') {
      setTemporaryStatus(data, 8000)
    }
  })

  on('agent:queued', (data) => {
    upsertInvokeStatus(data)
  })

  on('agent:thinking', (data) => {
    upsertInvokeStatus(data)
  })

  on('agent:typing', handleTyping)

  on('agent:stream', async (data) => {
    const existed = chatStore.messages.some((m) => m.id === data.message_id)
    handleStream(data)
    await nextTick()

    if (isAtBottom.value) {
      scrollToBottom()
      unreadCount.value = 0
      return
    }

    if (!existed) {
      unreadCount.value += 1
    }
  })

  on('agent:stream_end', async (data) => {
    handleStreamEnd(data)

    if (data?.source_message_id && data?.agent_role) {
      if (data.status === 'ok') {
        setTemporaryStatus(
          {
            source_message_id: data.source_message_id,
            agent_role: data.agent_role,
            status: 'completed',
            message: '回复完成',
          },
          3000
        )
      } else {
        setTemporaryStatus(
          {
            source_message_id: data.source_message_id,
            agent_role: data.agent_role,
            status: 'failed',
            message: '回复失败，请重试',
          },
          8000
        )
      }
    }

    await nextTick()

    if (isAtBottom.value) {
      scrollToBottom()
      unreadCount.value = 0
    }
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
    agentStore.clearTyping()
    invokeStatusMap.value = new Map()
    await reloadHistory()
  })

  connect()
})

onUnmounted(() => {
  disconnect()
  chatStore.clearMessages()
  agentStore.clearTyping()
  invokeStatusMap.value = new Map()
})
</script>
