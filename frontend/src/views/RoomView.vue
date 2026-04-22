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
      <WritingArea class="flex-1" />
    </div>

    <div class="w-[35%] flex flex-col border-r border-gray-200">
      <ChatPanel class="flex-1" />
    </div>

    <div class="w-[30%] min-h-0 flex flex-col gap-2 p-2">
      <TaskRequirements
        class="flex-1 min-h-0"
        :task="roomStore.currentTask"
        :loading="roomStore.loadingContext"
        :error="roomStore.contextError"
        :editable="authStore.isTeacher"
        :saving="roomStore.savingTask"
        :save-error="roomStore.taskSaveError"
        :save-success="taskSaveSuccess"
        @save="saveTaskPatch"
      />
      <TaskScript
        class="flex-1 min-h-0"
        :state="roomStore.taskScriptState"
        :loading="roomStore.loadingTaskScript"
        :error="roomStore.taskScriptError"
        :can-confirm="authStore.user?.role === 'student'"
        :requesting-proposal="roomStore.requestingTaskScriptProposal"
        :confirming-proposal="roomStore.confirmingTaskScriptProposal"
        @request-proposal="requestFacilitatorProposal"
        @confirm-proposal="confirmTaskScriptProposal"
      />
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth.js'
import { useRoomStore } from '../stores/room.js'
import WritingArea from '../components/layout/WritingArea.vue'
import ChatPanel from '../components/chat/ChatPanel.vue'
import TaskRequirements from '../components/task/TaskRequirements.vue'
import TaskScript from '../components/task/TaskScript.vue'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const roomStore = useRoomStore()
const taskSaveSuccess = computed(
  () => !!roomStore.taskSaveSuccessAt && !roomStore.savingTask && !roomStore.taskSaveError
)

function loadRoomContext() {
  const roomId = String(route.params.id || '')
  if (!roomId) return
  roomStore.loadRoomContext(roomId)
}

function leaveRoom() {
  router.push('/lobby')
}

async function saveTaskPatch(patch) {
  if (!authStore.isTeacher) return
  await roomStore.updateCurrentTask(patch)
}

async function requestFacilitatorProposal() {
  await roomStore.requestFacilitatorTaskScriptProposal()
}

async function confirmTaskScriptProposal(payload) {
  if (authStore.user?.role !== 'student') return
  await roomStore.confirmTaskScriptProposal(payload || {})
}

onMounted(loadRoomContext)
watch(() => route.params.id, loadRoomContext)
</script>
