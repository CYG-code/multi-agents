<template>
  <div class="border-t border-gray-200 p-3 bg-white">
    <div class="flex gap-2 items-end">
      <textarea
        v-model="inputText"
        @keydown="handleKeydown"
        placeholder="Type a message, press Enter to send"
        rows="2"
        class="flex-1 resize-none border border-gray-300 rounded-xl px-3 py-2 text-sm focus:outline-none focus:border-blue-400"
      />
      <button
        @click="sendMessage"
        class="px-4 py-2 bg-blue-500 text-white rounded-xl text-sm hover:bg-blue-600 transition-colors"
      >
        Send
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'

const emit = defineEmits(['send'])
const inputText = ref('')

function handleKeydown(event) {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    sendMessage()
  }
}

function sendMessage() {
  const content = inputText.value.trim()
  if (!content) return
  emit('send', content, [])
  inputText.value = ''
}
</script>
