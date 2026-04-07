<template>
  <Transition name="fade">
    <div
      v-if="typingRoles.length > 0"
      class="flex items-center gap-2 px-3 py-2 text-sm text-gray-500 border-t border-gray-100"
    >
      <div class="flex gap-1">
        <span
          v-for="i in 3"
          :key="i"
          class="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce"
          :style="{ animationDelay: `${i * 0.15}s` }"
        />
      </div>
      <span>{{ typingRoles.join('、') }} 正在输入...</span>
    </div>
  </Transition>
</template>

<script setup>
import { computed } from 'vue'
import { useAgentStore } from '../../stores/agent.js'

const agentStore = useAgentStore()

const ROLE_NAMES = {
  facilitator: '主持人',
  devil_advocate: '批判者',
  summarizer: '总结者',
  resource_finder: '资源者',
  encourager: '激励者',
}

const typingRoles = computed(() => {
  return Object.entries(agentStore.typingStatus)
    .filter(([, isTyping]) => isTyping)
    .map(([role]) => ROLE_NAMES[role] || role)
})
</script>

<style scoped>
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
