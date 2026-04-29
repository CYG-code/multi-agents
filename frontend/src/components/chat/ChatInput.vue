<template>
  <div class="relative border-t border-gray-200 bg-white p-3">
    <div v-if="selectedMentions.length > 0" class="mb-2 flex flex-wrap items-center gap-2">
      <span class="text-xs text-gray-500">已选智能体：</span>
      <button
        v-for="role in selectedMentions"
        :key="role"
        type="button"
        class="inline-flex items-center gap-1 rounded-full bg-blue-100 px-2 py-1 text-xs text-blue-700"
        @click="removeMention(role)"
      >
        @{{ roleLabel(role) }}
        <span class="text-blue-500">×</span>
      </button>
    </div>

    <div class="flex items-end gap-2">
      <div class="relative">
        <button
          type="button"
          class="rounded-xl border border-gray-300 px-3 py-2 text-sm transition-colors hover:bg-gray-50"
          @click="toggleMentionPanel"
        >
          @
        </button>

        <div
          v-if="showMentionPanel"
          class="absolute bottom-12 left-0 z-20 w-52 rounded-xl border border-gray-200 bg-white p-2 shadow-lg"
        >
          <p class="px-2 py-1 text-xs text-gray-500">选择智能体</p>
          <button
            v-for="agent in AGENT_OPTIONS"
            :key="agent.role"
            type="button"
            class="w-full rounded-lg px-2 py-1.5 text-left text-sm transition-colors hover:bg-gray-100"
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
        class="flex-1 resize-none rounded-xl border border-gray-300 px-3 py-2 text-sm focus:border-blue-400 focus:outline-none"
      />

      <button
        class="rounded-xl bg-blue-500 px-4 py-2 text-sm text-white transition-colors hover:bg-blue-600"
        @click="sendMessage"
      >
        发送
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'

const props = defineProps({
  agentBusy: {
    type: Boolean,
    default: false,
  },
  coolingRoles: {
    type: Array,
    default: () => [],
  },
})

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

  if (selectedMentions.value.some((role) => props.coolingRoles.includes(role))) {
    window.alert('当前智能体正在冷却中，请稍后再试。')
    return
  }

  if (props.agentBusy && selectedMentions.value.length > 0) {
    window.alert('当前有智能体正在排队或发言，请稍后再 @ 调用。')
    return
  }

  emit('send', content, selectedMentions.value)
  inputText.value = ''
  selectedMentions.value = []
  showMentionPanel.value = false
}
</script>
