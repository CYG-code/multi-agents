<template>
  <div class="relative flex h-screen overflow-hidden bg-gray-50">
    <button
      type="button"
      class="absolute top-3 right-3 z-30 px-3 py-1.5 text-sm rounded-lg border border-red-200 text-red-600 bg-white hover:bg-red-50 transition-colors"
      @click="leaveRoom"
    >
      退出房间
    </button>

    <div class="w-[35%] flex flex-col gap-2 p-2 border-r border-gray-200">
      <DiscussionArea class="flex-1" />
      <WritingArea class="flex-1" />
    </div>

    <div class="w-[35%] flex flex-col border-r border-gray-200">
      <ChatPanel class="flex-1" />
    </div>

    <div class="w-[30%] flex flex-col gap-2 p-2">
      <TaskRequirements class="flex-1" />
      <TaskScript class="flex-1" />
    </div>
  </div>
</template>

<script setup>
import { useRouter } from 'vue-router'
import DiscussionArea from '../components/layout/DiscussionArea.vue'
import WritingArea from '../components/layout/WritingArea.vue'
import ChatPanel from '../components/chat/ChatPanel.vue'
import TaskRequirements from '../components/task/TaskRequirements.vue'
import TaskScript from '../components/task/TaskScript.vue'

const router = useRouter()

function leaveRoom() {
  router.push('/lobby')
}
</script>
