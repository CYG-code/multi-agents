<template>
  <div class="flex h-full flex-col rounded-lg border border-gray-200 bg-white p-3">
    <div class="mb-2 flex items-center justify-between">
      <p class="text-xs font-semibold uppercase tracking-wide text-gray-400">任务流程</p>
      <button
        v-if="editable"
        type="button"
        class="rounded border border-blue-200 px-2 py-0.5 text-xs text-blue-600 hover:bg-blue-50 disabled:opacity-50"
        :disabled="saving"
        @click="saveScripts"
      >
        {{ saving ? '保存中...' : (task ? '保存' : '创建并保存') }}
      </button>
    </div>

    <div v-if="loading" class="flex flex-1 items-center justify-center text-sm text-gray-400">加载中...</div>
    <div v-else-if="error" class="flex flex-1 items-center justify-center text-sm text-red-500">{{ error }}</div>
    <div v-else-if="editable" class="min-h-0 flex flex-1 flex-col">
      <h3 class="mb-2 text-sm font-semibold text-gray-700">
        {{ task?.title || '当前房间未绑定任务，保存后将自动创建并绑定' }}
      </h3>
      <textarea
        v-model="draftScripts"
        rows="10"
        class="min-h-0 flex-1 resize-none rounded-md border border-gray-200 p-2 font-mono text-xs leading-5 text-gray-700 outline-none focus:border-blue-400"
        placeholder="请输入任务流程"
      />
      <p v-if="saveError" class="mt-2 text-xs text-red-500">{{ saveError }}</p>
      <p v-else-if="saveSuccess" class="mt-2 text-xs text-green-600">已保存</p>
    </div>
    <div v-else-if="!task" class="flex flex-1 items-center justify-center text-sm text-gray-400">当前房间未绑定任务</div>
    <div v-else class="min-h-0 flex-1 overflow-auto">
      <pre class="whitespace-pre-wrap break-words rounded-md bg-gray-50 p-2 text-xs leading-5 text-gray-700">{{ scriptsText }}</pre>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'

const props = defineProps({
  task: { type: Object, default: null },
  loading: { type: Boolean, default: false },
  error: { type: String, default: '' },
  editable: { type: Boolean, default: false },
  saving: { type: Boolean, default: false },
  saveError: { type: String, default: '' },
  saveSuccess: { type: Boolean, default: false },
})

const emit = defineEmits(['save'])
const draftScripts = ref('')

const scriptsText = computed(() => {
  const scripts = props.task?.scripts
  if (scripts == null || scripts === '') return '暂无任务流程'
  if (typeof scripts === 'string') return scripts
  try {
    return JSON.stringify(scripts, null, 2)
  } catch {
    return String(scripts)
  }
})

watch(
  () => props.task?.scripts,
  (value) => {
    if (value == null) {
      draftScripts.value = ''
      return
    }
    if (typeof value === 'string') {
      draftScripts.value = value
      return
    }
    try {
      draftScripts.value = JSON.stringify(value, null, 2)
    } catch {
      draftScripts.value = String(value)
    }
  },
  { immediate: true }
)

function saveScripts() {
  emit('save', { scripts: draftScripts.value.trim() || null })
}
</script>
