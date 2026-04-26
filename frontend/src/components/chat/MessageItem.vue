<template>
  <div v-if="isAgent" class="flex gap-2">
    <div
      :class="[
        'w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0',
        agentStyle.bg,
        agentStyle.text,
      ]"
    >
      {{ agentInitial }}
    </div>

    <div class="max-w-[80%]">
      <div class="flex items-center gap-2 mb-1">
        <span :class="['text-xs font-medium px-2 py-0.5 rounded-full', agentStyle.bg, agentStyle.text]">
          {{ agentStyle.label }}
        </span>
        <span v-if="replyTargetText" class="text-[11px] text-gray-500">
          回复 {{ replyTargetText }}
        </span>
        <span class="text-xs text-gray-400">{{ formatTime(message.created_at) }}</span>
      </div>

      <div v-if="sourcePreviewText" class="mb-1 text-[11px] text-gray-500">
        针对问题：{{ sourcePreviewText }}
      </div>

      <div class="bg-gray-50 border border-gray-200 rounded-2xl rounded-tl-sm px-3 py-2 text-sm text-gray-800">
        <span class="message-markdown" v-html="renderedContent" />
        <span
          v-if="message.status === 'streaming'"
          class="inline-block w-0.5 h-4 bg-gray-600 animate-pulse ml-0.5"
        />
      </div>
    </div>
  </div>

  <div v-else :class="['flex gap-2', isSelf ? 'flex-row-reverse' : 'flex-row']">
    <div
      class="w-8 h-8 rounded-full bg-blue-400 flex items-center justify-center text-white text-sm font-bold flex-shrink-0"
    >
      {{ avatarText }}
    </div>

    <div class="max-w-[70%] flex flex-col" :class="isSelf ? 'items-end' : 'items-start'">
      <span class="text-xs text-gray-500 mb-1">{{ message.display_name || 'Unknown' }}</span>

      <div
        :class="[
          'px-3 py-2 rounded-2xl text-sm leading-relaxed break-words',
          isSelf
            ? 'bg-blue-500 text-white rounded-tr-sm'
            : 'bg-white border border-gray-200 text-gray-800 rounded-tl-sm',
        ]"
      >
        <span class="message-markdown" v-html="renderedContent" />
      </div>

      <span class="text-xs text-gray-400 mt-1">{{ formatTime(message.created_at) }}</span>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useAuthStore } from '../../stores/auth.js'
import { useChatStore } from '../../stores/chat.js'

const props = defineProps({
  message: {
    type: Object,
    required: true,
  },
})

const authStore = useAuthStore()
const chatStore = useChatStore()

const AGENT_COLORS = {
  facilitator: { bg: 'bg-indigo-100', text: 'text-indigo-700', label: 'Facilitator' },
  devil_advocate: { bg: 'bg-red-100', text: 'text-red-700', label: 'Devil Advocate' },
  summarizer: { bg: 'bg-blue-100', text: 'text-blue-700', label: 'Summarizer' },
  resource_finder: { bg: 'bg-green-100', text: 'text-green-700', label: 'Resource Finder' },
  encourager: { bg: 'bg-yellow-100', text: 'text-yellow-700', label: 'Encourager' },
}

const isAgent = computed(() => props.message.sender_type === 'agent')
const isSelf = computed(() => props.message.sender_id === authStore.user?.id)

const agentStyle = computed(() => {
  return AGENT_COLORS[props.message.agent_role] || { bg: 'bg-gray-100', text: 'text-gray-700', label: 'AI' }
})

const agentInitial = computed(() => {
  const label = agentStyle.value.label || 'AI'
  return label.charAt(0).toUpperCase()
})

const avatarText = computed(() => {
  const first = (props.message.display_name || '?').trim().charAt(0)
  return first ? first.toUpperCase() : '?'
})

const renderedContent = computed(() => renderBasicMarkdown(props.message.content || ''))
const sourceMessage = computed(() => {
  const sourceId = props.message?.source_message_id
  if (!sourceId) return null
  return chatStore.messages.find((m) => m.id === sourceId) || null
})

const replyTargetText = computed(() => {
  if (!isAgent.value || !sourceMessage.value) return ''
  return sourceMessage.value.display_name || '某位同学'
})

const sourcePreviewText = computed(() => {
  if (!isAgent.value || !sourceMessage.value?.content) return ''
  const raw = sourceMessage.value.content.replace(/\s+/g, ' ').trim()
  if (!raw) return ''
  return raw.length > 36 ? `${raw.slice(0, 36)}...` : raw
})

function escapeHtml(text) {
  return text
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;')
}

function renderBasicMarkdown(text) {
  const safe = escapeHtml(text)

  // Support **bold** while keeping output XSS-safe.
  const withBold = safe.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
  return withBold.replace(/\r?\n/g, '<br />')
}

function formatTime(value) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}
</script>

<style scoped>
.message-markdown :deep(strong) {
  font-weight: 700;
}
</style>
