<template>
  <div class="border-t border-gray-200 p-3 bg-white relative">
    <div class="mb-2 flex flex-wrap items-center gap-2" v-if="selectedMentions.length > 0">
      <span class="text-xs text-gray-500">已选智能体：</span>
      <button
        v-for="role in selectedMentions"
        :key="role"
        type="button"
        class="inline-flex items-center gap-1 px-2 py-1 rounded-full bg-blue-100 text-blue-700 text-xs"
        @click="removeMention(role)"
      >
        @{{ roleLabel(role) }}
        <span class="text-blue-500">×</span>
      </button>
    </div>

    <div class="flex gap-2 items-end">
      <div class="relative">
        <button
          type="button"
          class="px-3 py-2 border border-gray-300 rounded-xl text-sm hover:bg-gray-50 transition-colors"
          @click="toggleMentionPanel"
        >
          @
        </button>

        <div
          v-if="showMentionPanel"
          class="absolute bottom-12 left-0 w-52 bg-white border border-gray-200 rounded-xl shadow-lg p-2 z-20"
        >
          <p class="text-xs text-gray-500 px-2 py-1">选择智能体</p>
          <button
            v-for="agent in AGENT_OPTIONS"
            :key="agent.role"
            type="button"
            class="w-full text-left px-2 py-1.5 rounded-lg text-sm hover:bg-gray-100 transition-colors"
            @click="toggleMention(agent.role)"
          >
            @{{ agent.label }}
          </button>
        </div>
      </div>

      <textarea
        v-model="inputText"
        @keydown="handleKeydown"
        placeholder="输入消息，回车发送"
        rows="2"
        class="flex-1 resize-none border border-gray-300 rounded-xl px-3 py-2 text-sm focus:outline-none focus:border-blue-400"
      />

      <button
        @click="sendMessage"
        class="px-4 py-2 bg-blue-500 text-white rounded-xl text-sm hover:bg-blue-600 transition-colors"
      >
        发送
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'

const emit = defineEmits(['send'])

const AGENT_OPTIONS = [
  { role: 'facilitator', label: '主持人' },
  { role: 'devil_advocate', label: '批判者' },
  { role: 'summarizer', label: '总结者' },
  { role: 'resource_finder', label: '资源检索者' },
  { role: 'encourager', label: '鼓励者' },
]

const inputText = ref('')
const selectedMentions = ref([])
const showMentionPanel = ref(false)

function roleLabel(role) {
  const found = AGENT_OPTIONS.find((it) => it.role === role)
  return found ? found.label : role
}

function toggleMentionPanel() {
  showMentionPanel.value = !showMentionPanel.value
}

function toggleMention(role) {
  if (selectedMentions.value.includes(role)) {
    selectedMentions.value = selectedMentions.value.filter((item) => item !== role)
  } else {
    selectedMentions.value = [...selectedMentions.value, role]
  }
  // 选中后自动关闭面板，避免每次手动收起
  showMentionPanel.value = false
}

function removeMention(role) {
  selectedMentions.value = selectedMentions.value.filter((item) => item !== role)
}

function handleKeydown(event) {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    sendMessage()
  }
}

function sendMessage() {
  const content = inputText.value.trim()
  if (!content) return
  emit('send', content, selectedMentions.value)
  inputText.value = ''
  selectedMentions.value = []
  showMentionPanel.value = false
}
</script>
