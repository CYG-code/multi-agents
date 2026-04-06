<template>
  <div :class="['flex gap-2', isSelf ? 'flex-row-reverse' : 'flex-row']">
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
        {{ message.content }}
      </div>

      <span class="text-xs text-gray-400 mt-1">{{ formatTime(message.created_at) }}</span>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useAuthStore } from '../../stores/auth.js'

const props = defineProps({
  message: {
    type: Object,
    required: true,
  },
})

const authStore = useAuthStore()

const isSelf = computed(() => props.message.sender_id === authStore.user?.id)
const avatarText = computed(() => {
  const first = (props.message.display_name || '?').trim().charAt(0)
  return first ? first.toUpperCase() : '?'
})

function formatTime(value) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}
</script>

