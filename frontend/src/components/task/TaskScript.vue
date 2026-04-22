<template>
  <div class="flex h-full min-h-0 flex-col rounded-lg border border-gray-200 bg-white p-3 overflow-hidden">
    <div class="mb-3 flex items-center justify-between">
      <p class="text-xs font-semibold uppercase tracking-wide text-gray-400">任务流程</p>
      <button
        type="button"
        class="rounded border border-indigo-200 px-2 py-1 text-xs text-indigo-600 hover:bg-indigo-50 disabled:cursor-not-allowed disabled:opacity-50"
        :disabled="loading || requestingProposal || !taskId"
        @click="$emit('request-proposal')"
      >
        {{ requestingProposal ? '主持智能体生成中...' : '让主持智能体更新建议' }}
      </button>
    </div>

    <div v-if="loading" class="flex flex-1 items-center justify-center text-sm text-gray-400">加载中...</div>
    <div v-else-if="error" class="mb-2 rounded border border-red-200 bg-red-50 p-2 text-xs text-red-600">{{ error }}</div>
    <div v-else class="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto pr-1">
      <div class="rounded-md border border-gray-200 bg-gray-50 p-2">
        <p class="mb-1 text-xs font-semibold text-gray-500">当前状态</p>
        <p class="text-sm text-gray-700">{{ currentStatus || '暂无' }}</p>
      </div>

      <div class="rounded-md border border-blue-200 bg-blue-50 p-2">
        <p class="mb-1 text-xs font-semibold text-blue-600">下一步目标</p>
        <p class="text-sm text-blue-800">{{ nextGoal || '暂无' }}</p>
      </div>

      <div v-if="pendingProposal" class="rounded-md border border-amber-200 bg-amber-50 p-2">
        <p class="mb-1 text-xs font-semibold text-amber-700">待确认变更（主持智能体）</p>
        <p class="text-[11px] text-amber-700">学生可编辑建议后再确认</p>
        <label class="mt-2 block text-xs text-amber-800">状态建议（可调整）</label>
        <textarea
          v-model="editableCurrentStatus"
          :disabled="!canConfirm || confirmingProposal"
          rows="2"
          class="mt-1 w-full resize-y rounded border border-amber-200 bg-white p-1.5 text-xs text-gray-700 outline-none focus:border-amber-400 disabled:cursor-not-allowed disabled:bg-amber-100"
        />
        <label class="mt-2 block text-xs text-amber-800">目标建议（可调整）</label>
        <textarea
          v-model="editableNextGoal"
          :disabled="!canConfirm || confirmingProposal"
          rows="2"
          class="mt-1 w-full resize-y rounded border border-amber-200 bg-white p-1.5 text-xs text-gray-700 outline-none focus:border-amber-400 disabled:cursor-not-allowed disabled:bg-amber-100"
        />
        <p v-if="pendingProposal.change_reason" class="mt-1 text-xs text-amber-600">
          调整理由：{{ pendingProposal.change_reason }}
        </p>
        <label class="mt-2 block text-xs text-amber-800">学生意见（可选）</label>
        <textarea
          v-model="studentFeedback"
          :disabled="!canConfirm || confirmingProposal"
          rows="2"
          placeholder="例如：建议把目标拆成两步，先做数据收集"
          class="mt-1 w-full resize-y rounded border border-amber-200 bg-white p-1.5 text-xs text-gray-700 outline-none focus:border-amber-400 disabled:cursor-not-allowed disabled:bg-amber-100"
        />
        <div class="mt-2 flex items-center justify-between gap-2">
          <span class="text-[11px] text-amber-600">每次变更都需要学生确认后才会生效</span>
          <button
            type="button"
            class="rounded border border-green-200 bg-white px-2 py-1 text-xs text-green-700 hover:bg-green-50 disabled:cursor-not-allowed disabled:opacity-50"
            :disabled="!canConfirm || confirmingProposal || !editableCurrentStatus.trim() || !editableNextGoal.trim()"
            @click="confirmProposal"
          >
            {{ confirmingProposal ? '确认中...' : '确认并保存' }}
          </button>
        </div>
        <p v-if="!canConfirm" class="mt-1 text-[11px] text-amber-600">仅学生可以确认此提案</p>
      </div>

    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'

const props = defineProps({
  state: { type: Object, default: null },
  loading: { type: Boolean, default: false },
  error: { type: String, default: '' },
  canConfirm: { type: Boolean, default: false },
  requestingProposal: { type: Boolean, default: false },
  confirmingProposal: { type: Boolean, default: false },
})

const emit = defineEmits(['request-proposal', 'confirm-proposal'])

const taskId = computed(() => props.state?.task_id || null)
const currentStatus = computed(() => props.state?.current_status || '')
const nextGoal = computed(() => props.state?.next_goal || '')
const pendingProposal = computed(() => props.state?.pending_proposal || null)
const editableCurrentStatus = ref('')
const editableNextGoal = ref('')
const studentFeedback = ref('')

watch(
  pendingProposal,
  (value) => {
    if (!value) {
      editableCurrentStatus.value = ''
      editableNextGoal.value = ''
      studentFeedback.value = ''
      return
    }
    editableCurrentStatus.value = value.current_status || ''
    editableNextGoal.value = value.next_goal || ''
    studentFeedback.value = ''
  },
  { immediate: true }
)
function confirmProposal() {
  emit('confirm-proposal', {
    current_status: editableCurrentStatus.value.trim(),
    next_goal: editableNextGoal.value.trim(),
    student_feedback: studentFeedback.value.trim() || null,
  })
}
</script>
