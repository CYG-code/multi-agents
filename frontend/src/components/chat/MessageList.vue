<template>
  <div ref="listRef" class="h-full overflow-y-auto p-3 space-y-2" @scroll="handleScroll">
    <div v-if="hasMore" class="text-center">
      <button @click="emit('load-more')" class="text-xs text-blue-500 hover:underline">
        Load more history
      </button>
    </div>

    <MessageItem v-for="msg in messages" :key="msg.id" :message="msg" />
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import MessageItem from './MessageItem.vue'

const props = defineProps({
  messages: {
    type: Array,
    default: () => [],
  },
  hasMore: {
    type: Boolean,
    default: false,
  },
})

const emit = defineEmits(['load-more', 'viewport-change'])
const listRef = ref(null)
const BOTTOM_THRESHOLD = 24

function isNearBottom() {
  if (!listRef.value) return true
  const { scrollTop, scrollHeight, clientHeight } = listRef.value
  return scrollHeight - (scrollTop + clientHeight) <= BOTTOM_THRESHOLD
}

function handleScroll() {
  emit('viewport-change', { atBottom: isNearBottom() })
}

function scrollToBottom() {
  if (listRef.value) {
    listRef.value.scrollTop = listRef.value.scrollHeight
    emit('viewport-change', { atBottom: true })
  }
}

onMounted(() => {
  // Initialize parent state with current viewport position.
  emit('viewport-change', { atBottom: isNearBottom(), count: props.messages.length })
})

defineExpose({ scrollToBottom, isNearBottom })
</script>
