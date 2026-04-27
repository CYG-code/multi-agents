<template>
  <div class="flex h-full min-h-0 flex-col rounded-lg border border-gray-200 bg-white p-3 overflow-hidden">
    <div class="mb-3 flex items-center justify-between">
      <p class="text-xs font-semibold uppercase tracking-wide text-gray-400">{{ TXT.title }}</p>
      <button
        type="button"
        class="rounded border border-indigo-200 px-2 py-1 text-xs text-indigo-600 hover:bg-indigo-50 disabled:cursor-not-allowed disabled:opacity-50"
        :disabled="loading || requestingProposal || !taskId || !!pendingProposal"
        @click="$emit('request-proposal')"
      >
        {{ requestingProposal ? TXT.requesting : TXT.requestButton }}
      </button>
    </div>

    <div v-if="loading" class="flex flex-1 items-center justify-center text-sm text-gray-400">{{ TXT.loading }}</div>
    <div v-else class="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto pr-1">
      <div v-if="error" class="rounded border border-red-200 bg-red-50 p-2 text-xs text-red-600">
        {{ error }}
      </div>
      <div v-if="lockNotice" class="rounded border border-amber-200 bg-amber-50 p-2 text-xs text-amber-700">
        <div class="flex items-center justify-between gap-2">
          <span>{{ lockNotice }}</span>
          <button
            v-if="showRetryAcquire"
            type="button"
            class="shrink-0 rounded border border-amber-300 bg-white px-2 py-0.5 text-[11px] text-amber-700 hover:bg-amber-100 disabled:cursor-not-allowed disabled:opacity-50"
            :disabled="acquiringLock || !!(lockState?.locked && !lockState?.is_mine)"
            @click="$emit('acquire-lock')"
          >
            {{ acquiringLock ? TXT.retryingAcquire : TXT.retryAcquire }}
          </button>
        </div>
      </div>

      <div class="rounded-md border border-gray-200 bg-gray-50 p-2">
        <p class="mb-1 text-xs font-semibold text-gray-500">{{ TXT.currentStatus }}</p>
        <p class="text-sm text-gray-700">{{ currentStatus || TXT.empty }}</p>
      </div>

      <div class="rounded-md border border-blue-200 bg-blue-50 p-2">
        <p class="mb-1 text-xs font-semibold text-blue-600">{{ TXT.nextGoal }}</p>
        <p class="text-sm text-blue-800">{{ nextGoal || TXT.empty }}</p>
      </div>

      <div v-if="pendingProposal" class="rounded-md border border-amber-200 bg-amber-50 p-2">
        <p class="mb-1 text-xs font-semibold text-amber-700">{{ TXT.pendingTitle }}</p>
        <p class="text-[11px] text-amber-700">{{ TXT.pendingHint }}</p>

        <div class="mt-2 rounded border border-amber-200 bg-white p-2 text-[11px] text-amber-800">
          <div v-if="lockState?.locked">
            <span v-if="hasEditLock">{{ TXT.lockMine }}</span>
            <span v-else>{{ TXT.lockBy }} {{ lockState.owner_display_name || TXT.otherStudent }} {{ TXT.lockEditing }}</span>
          </div>
          <div v-else>{{ TXT.noLock }}</div>
        </div>

        <div class="mt-2 flex items-center gap-2">
          <button
            v-if="canConfirm && !hasEditLock"
            type="button"
            class="rounded border border-amber-300 bg-white px-2 py-1 text-xs text-amber-700 hover:bg-amber-100 disabled:cursor-not-allowed disabled:opacity-50"
            :disabled="acquiringLock || !!confirmingProposal || !!(lockState?.locked && !lockState?.is_mine)"
            @click="$emit('acquire-lock')"
          >
            {{ acquiringLock ? TXT.acquiring : TXT.enterEdit }}
          </button>

          <button
            v-if="canConfirm && hasEditLock"
            type="button"
            class="rounded border border-gray-300 bg-white px-2 py-1 text-xs text-gray-700 hover:bg-gray-100 disabled:cursor-not-allowed disabled:opacity-50"
            :disabled="releasingLock || !!confirmingProposal"
            @click="$emit('release-lock')"
          >
            {{ releasingLock ? TXT.releasing : TXT.exitEdit }}
          </button>
        </div>

        <label class="mt-2 block text-xs text-amber-800">{{ TXT.editStatus }}</label>
        <textarea
          v-model="editableCurrentStatus"
          :disabled="!canEdit"
          rows="2"
          class="mt-1 w-full resize-y rounded border border-amber-200 bg-white p-1.5 text-xs text-gray-700 outline-none focus:border-amber-400 disabled:cursor-not-allowed disabled:bg-amber-100"
        />

        <label class="mt-2 block text-xs text-amber-800">{{ TXT.editGoal }}</label>
        <textarea
          v-model="editableNextGoal"
          :disabled="!canEdit"
          rows="2"
          class="mt-1 w-full resize-y rounded border border-amber-200 bg-white p-1.5 text-xs text-gray-700 outline-none focus:border-amber-400 disabled:cursor-not-allowed disabled:bg-amber-100"
        />

        <p v-if="pendingProposal.change_reason" class="mt-1 text-xs text-amber-600">
          {{ TXT.reason }}: {{ pendingProposal.change_reason }}
        </p>

        <label class="mt-2 block text-xs text-amber-800">{{ TXT.feedback }}</label>
        <textarea
          v-model="studentFeedback"
          :disabled="!canEdit"
          rows="2"
          :placeholder="TXT.feedbackPlaceholder"
          class="mt-1 w-full resize-y rounded border border-amber-200 bg-white p-1.5 text-xs text-gray-700 outline-none focus:border-amber-400 disabled:cursor-not-allowed disabled:bg-amber-100"
        />

        <div class="mt-2 flex items-center justify-between gap-2">
          <span class="text-[11px] text-amber-600">{{ TXT.singleConfirmHint }}</span>
          <button
            type="button"
            class="rounded border border-green-200 bg-white px-2 py-1 text-xs text-green-700 hover:bg-green-50 disabled:cursor-not-allowed disabled:opacity-50"
            :disabled="!canConfirmAction"
            @click="confirmProposal"
          >
            {{ confirmButtonText }}
          </button>
        </div>

        <p v-if="!canConfirm" class="mt-1 text-[11px] text-amber-600">{{ TXT.onlyStudent }}</p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'

const TXT = {
  title: '\u4efb\u52a1\u6d41\u7a0b',
  requestButton: '\u8ba9\u4e3b\u6301\u667a\u80fd\u4f53\u66f4\u65b0\u5efa\u8bae',
  requesting: '\u4e3b\u6301\u667a\u80fd\u4f53\u751f\u6210\u4e2d...',
  loading: '\u52a0\u8f7d\u4e2d...',
  currentStatus: '\u5f53\u524d\u72b6\u6001',
  nextGoal: '\u4e0b\u4e00\u6b65\u76ee\u6807',
  empty: '\u6682\u65e0',
  pendingTitle: '\u5f85\u786e\u8ba4\u53d8\u66f4\uff08\u4e3b\u6301\u667a\u80fd\u4f53\uff09',
  pendingHint: '\u5b66\u751f\u5355\u4eba\u7f16\u8f91\u5e76\u786e\u8ba4\u540e\u751f\u6548\uff0c\u540c\u4e00\u65f6\u523b\u4ec5\u5141\u8bb8\u4e00\u4f4d\u5b66\u751f\u7f16\u8f91\u3002',
  lockMine: '\u4f60\u6b63\u5728\u7f16\u8f91\u8be5\u63d0\u6848',
  lockBy: '\u5f53\u524d\u7531',
  lockEditing: '\u7f16\u8f91\u4e2d',
  otherStudent: '\u5176\u4ed6\u540c\u5b66',
  noLock: '\u5f53\u524d\u65e0\u4eba\u7f16\u8f91',
  retryAcquire: '\u91cd\u8bd5\u8fdb\u5165\u7f16\u8f91',
  retryingAcquire: '\u91cd\u8bd5\u4e2d...',
  enterEdit: '\u8fdb\u5165\u7f16\u8f91',
  acquiring: '\u8fdb\u5165\u7f16\u8f91\u4e2d...',
  exitEdit: '\u9000\u51fa\u7f16\u8f91',
  releasing: '\u9000\u51fa\u4e2d...',
  editStatus: '\u72b6\u6001\u5efa\u8bae\uff08\u53ef\u8c03\u6574\uff09',
  editGoal: '\u76ee\u6807\u5efa\u8bae\uff08\u53ef\u8c03\u6574\uff09',
  reason: '\u8c03\u6574\u7406\u7531',
  feedback: '\u5b66\u751f\u610f\u89c1\uff08\u53ef\u9009\uff09',
  feedbackPlaceholder: '\u4f8b\u5982\uff1a\u5efa\u8bae\u628a\u76ee\u6807\u62c6\u6210\u4e24\u6b65\uff0c\u5148\u505a\u6570\u636e\u6536\u96c6\u3002',
  singleConfirmHint: '\u5f53\u524d\u7f16\u8f91\u8005\u786e\u8ba4\u540e\u7acb\u5373\u751f\u6548\u3002',
  onlyStudent: '\u4ec5\u5b66\u751f\u53ef\u786e\u8ba4\u6b64\u63d0\u6848',
  submit: '\u786e\u8ba4\u5e76\u63d0\u4ea4',
  submitting: '\u63d0\u4ea4\u4e2d...',
}

const props = defineProps({
  state: { type: Object, default: null },
  loading: { type: Boolean, default: false },
  error: { type: String, default: '' },
  lockNotice: { type: String, default: '' },
  canConfirm: { type: Boolean, default: false },
  requestingProposal: { type: Boolean, default: false },
  confirmingProposal: { type: Boolean, default: false },
  lockState: { type: Object, default: null },
  hasEditLock: { type: Boolean, default: false },
  acquiringLock: { type: Boolean, default: false },
  releasingLock: { type: Boolean, default: false },
  currentUserId: { type: String, default: '' },
})

const emit = defineEmits(['request-proposal', 'confirm-proposal', 'acquire-lock', 'release-lock'])

const taskId = computed(() => props.state?.task_id || null)
const currentStatus = computed(() => props.state?.current_status || '')
const nextGoal = computed(() => props.state?.next_goal || '')
const pendingProposal = computed(() => props.state?.pending_proposal || null)
const currentProposalId = computed(() => pendingProposal.value?.id || '')

const editableCurrentStatus = ref('')
const editableNextGoal = ref('')
const studentFeedback = ref('')
const draftsByProposalId = ref({})

const canEdit = computed(() => {
  return !!props.canConfirm && !!props.hasEditLock && !props.confirmingProposal
})

const canConfirmAction = computed(() => {
  if (!props.canConfirm || props.confirmingProposal) return false
  if (!props.hasEditLock) return false
  if (!editableCurrentStatus.value.trim() || !editableNextGoal.value.trim()) return false
  return true
})

const confirmButtonText = computed(() => {
  if (props.confirmingProposal) return TXT.submitting
  return TXT.submit
})

const showRetryAcquire = computed(() => {
  return !!props.canConfirm && !props.hasEditLock && !!pendingProposal.value
})

function persistDraft() {
  const proposalId = currentProposalId.value
  if (!proposalId) return
  draftsByProposalId.value = {
    ...draftsByProposalId.value,
    [proposalId]: {
      current_status: editableCurrentStatus.value,
      next_goal: editableNextGoal.value,
      student_feedback: studentFeedback.value,
    },
  }
}

watch(
  currentProposalId,
  (proposalId) => {
    if (!proposalId) {
      editableCurrentStatus.value = ''
      editableNextGoal.value = ''
      studentFeedback.value = ''
      return
    }

    const draft = draftsByProposalId.value[proposalId]
    if (draft) {
      editableCurrentStatus.value = draft.current_status || ''
      editableNextGoal.value = draft.next_goal || ''
      studentFeedback.value = draft.student_feedback || ''
      return
    }

    editableCurrentStatus.value = pendingProposal.value?.current_status || ''
    editableNextGoal.value = pendingProposal.value?.next_goal || ''
    studentFeedback.value = ''
    persistDraft()
  },
  { immediate: true }
)

watch([editableCurrentStatus, editableNextGoal, studentFeedback], () => {
  persistDraft()
})

function confirmProposal() {
  const payload = {
    proposal_id: pendingProposal.value?.id || null,
  }
  if (props.hasEditLock) {
    payload.current_status = editableCurrentStatus.value.trim()
    payload.next_goal = editableNextGoal.value.trim()
    payload.student_feedback = studentFeedback.value.trim() || null
  }
  emit('confirm-proposal', payload)
}
</script>
