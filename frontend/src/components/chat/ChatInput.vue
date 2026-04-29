<template>
  <div class="relative border-t border-gray-200 bg-white p-3">
    <div v-if="selectedMentions.length > 0" class="mb-2 flex flex-wrap items-center gap-2">
      <span class="text-xs text-gray-500">Selected agents:</span>
      <button
        v-for="role in selectedMentions"
        :key="role"
        type="button"
        class="inline-flex items-center gap-1 rounded-full bg-blue-100 px-2 py-1 text-xs text-blue-700"
        @click="removeMention(role)"
      >
        @{{ roleLabel(role) }}
        <span class="text-blue-500">x</span>
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
          <p class="px-2 py-1 text-xs text-gray-500">Choose an agent</p>
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
        placeholder="Type message, Enter to send"
        rows="2"
        class="flex-1 resize-none rounded-xl border border-gray-300 px-3 py-2 text-sm focus:border-blue-400 focus:outline-none"
      />

      <button
        class="rounded-xl bg-blue-500 px-4 py-2 text-sm text-white transition-colors hover:bg-blue-600"
        @click="sendMessage"
      >
        Send
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
  cooldownUntilByRole: {
    type: Object,
    default: () => ({}),
  },
})

const emit = defineEmits(['send'])

const AGENT_OPTIONS = [
  { role: 'facilitator', label: 'Facilitator' },
  { role: 'devil_advocate', label: 'Devil Advocate' },
  { role: 'summarizer', label: 'Summarizer' },
  { role: 'resource_finder', label: 'Resource Finder' },
  { role: 'encourager', label: 'Encourager' },
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

  const now = Date.now()
  const coolingRole = selectedMentions.value.find((role) => {
    const until = Number(props.cooldownUntilByRole?.[role] || 0)
    return Number.isFinite(until) && until > now
  })
  if (coolingRole) {
    const until = Number(props.cooldownUntilByRole?.[coolingRole] || 0)
    const remainSeconds = Math.max(1, Math.ceil((until - now) / 1000))
    window.alert(`Current agent is cooling down, about ${remainSeconds} seconds remaining.`)
    return
  }

  if (props.agentBusy && selectedMentions.value.length > 0) {
    window.alert('An agent is still busy, please try again in a moment.')
    return
  }

  emit('send', content, selectedMentions.value)
  inputText.value = ''
  selectedMentions.value = []
  showMentionPanel.value = false
}
</script>
