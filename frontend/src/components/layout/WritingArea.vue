<template>
  <div class="flex h-full flex-col rounded-lg border border-gray-200 bg-white p-3">
    <div class="mb-2 flex items-center justify-between">
      <p class="text-xs font-semibold uppercase tracking-wide text-gray-400">写作区</p>
      <span class="text-xs text-gray-400">{{ wordCount }} 字</span>
    </div>

    <div class="mb-2 flex flex-wrap items-center gap-1 rounded-md border border-gray-200 bg-gray-50 p-1.5">
      <button
        type="button"
        class="rounded border border-gray-200 bg-white px-2 py-1 text-xs text-gray-600 hover:bg-gray-100"
        @mousedown.prevent="applyCommand('bold')"
      >
        加粗
      </button>
      <button
        type="button"
        class="rounded border border-gray-200 bg-white px-2 py-1 text-xs text-gray-600 hover:bg-gray-100"
        @mousedown.prevent="applyCommand('italic')"
      >
        斜体
      </button>
      <button
        type="button"
        class="rounded border border-gray-200 bg-white px-2 py-1 text-xs text-gray-600 hover:bg-gray-100"
        @mousedown.prevent="applyCommand('underline')"
      >
        下划线
      </button>
      <button
        type="button"
        class="ml-1 inline-flex items-center gap-2 rounded border border-gray-200 bg-white px-2 py-1 text-xs text-gray-600 hover:bg-gray-100"
        @mousedown.prevent="applyColor"
      >
        <span>颜色</span>
        <input
          v-model="currentColor"
          type="color"
          class="h-4 w-5 cursor-pointer rounded border border-gray-200 bg-white p-0"
          @mousedown.stop="saveSelection"
          @click.stop
          @input.stop="handleColorChange"
        />
      </button>
      <button
        type="button"
        class="ml-auto rounded border border-indigo-200 bg-white px-2 py-1 text-xs text-indigo-600 hover:bg-indigo-50"
        @click="toggleHistory"
      >
        {{ historyPanelOpen ? '收起历史' : '版本历史' }}
      </button>
      <button
        v-if="isStudent"
        type="button"
        class="rounded border border-emerald-200 bg-white px-2 py-1 text-xs text-emerald-600 hover:bg-emerald-50 disabled:opacity-60"
        :disabled="savingVersion"
        @click="saveVersion"
      >
        {{ savingVersion ? '保存中...' : '保存版本' }}
      </button>
    </div>

    <div class="mb-2 rounded border border-sky-200 bg-sky-50 px-2 py-1 text-[11px] text-sky-700">
      <span v-if="otherEditingNames.length === 0">当前仅你在编辑或暂无其他同学编辑</span>
      <span v-else>正在编辑：{{ otherEditingNames.join('、') }}</span>
    </div>

    <div
      ref="editorRef"
      class="writing-editor min-h-0 flex-1 overflow-auto rounded-md border border-gray-200 p-3 text-sm text-gray-700 outline-none focus:border-blue-400"
      contenteditable="true"
      @input="handleInput"
      @keydown="handleKeydown"
      @mouseup="saveSelection"
      @keyup="saveSelection"
      @blur="handleBlur"
      @focus="handleFocus"
    ></div>

    <div v-if="historyPanelOpen" class="mt-2 max-h-44 overflow-auto rounded border border-gray-200 bg-gray-50 p-2">
      <p class="mb-2 text-xs font-semibold text-gray-600">写作区版本历史</p>
      <p v-if="loadingHistory" class="text-xs text-gray-400">加载中...</p>
      <p v-else-if="historyItems.length === 0" class="text-xs text-gray-400">暂无历史</p>
      <div v-else class="space-y-1">
        <div v-for="item in historyItems" :key="item.version" class="rounded border border-gray-200 bg-white px-2 py-1">
          <div class="flex items-center justify-between gap-2">
            <span class="text-[11px] text-gray-600">v{{ item.version }} · {{ formatWhen(item.saved_at || item.updated_at) }} · {{ item.saved_by_display_name || item.updated_by_display_name || '未知用户' }}</span>
            <button
              v-if="isTeacher"
              type="button"
              class="rounded border border-amber-300 px-2 py-0.5 text-[11px] text-amber-700 hover:bg-amber-50 disabled:opacity-60"
              :disabled="restoringVersion === item.version"
              @click="restoreVersion(item.version)"
            >
              {{ restoringVersion === item.version ? '回滚中...' : '回滚到此版本' }}
            </button>
          </div>
        </div>
      </div>
    </div>

    <div class="mt-2 rounded-md border border-amber-200 bg-amber-50 px-2 py-1.5 text-[11px] text-amber-700">
      提交进度：{{ confirmCount }}/{{ requiredConfirmations }} 人确认
      <span v-if="isMeConfirmed">（你已确认）</span>
      <span v-if="isFinalSubmitted">，已最终提交</span>
    </div>

    <div class="mt-2 flex items-center justify-between">
      <p class="text-xs text-gray-400">{{ saveHint }}</p>
      <button
        type="button"
        class="rounded-md px-3 py-1.5 text-xs text-white disabled:opacity-60"
        :class="isFinalSubmitted ? 'bg-green-600' : 'bg-blue-600 hover:bg-blue-700'"
        :disabled="!canConfirmSubmit"
        @click="confirmSubmit"
      >
        {{ submitButtonText }}
      </button>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useAuthStore } from '../../stores/auth.js'
import { useRoomStore } from '../../stores/room.js'
import { roomApi } from '../../services/roomApi.js'
import { useWebSocket } from '../../composables/useWebSocket.js'

const route = useRoute()
const authStore = useAuthStore()
const roomStore = useRoomStore()
const roomId = String(route.params.id || '')
const { connect, on, send, disconnect, connected } = useWebSocket(roomId)

const editorRef = ref(null)
const htmlDraft = ref('')
const plainText = ref('')
const lastSavedAt = ref(null)
const currentColor = ref('#1f2937')
const savedRange = ref(null)
const lastActivityReportAt = ref(0)
const lastLocalEditAt = ref(0)
const lastAwarenessSentAt = ref(0)
const docVersion = ref(0)
const awarenessMap = ref({})
const historyPanelOpen = ref(false)
const historyItems = ref([])
const loadingHistory = ref(false)
const restoringVersion = ref(0)
const savingVersion = ref(false)
const undoStack = ref([])
const redoStack = ref([])

const ACTIVITY_REPORT_INTERVAL_MS = 12000
const AWARENESS_SEND_INTERVAL_MS = 2000
const AWARENESS_STALE_MS = 8000
const UNDO_STACK_MAX = 50

let wsSendTimer = null
let awarenessCleaner = null
let awarenessHeartbeat = null

const storageKey = computed(() => `room:${roomId}:writing_draft`)

const isTeacher = computed(() => authStore.isTeacher)

const writingState = computed(() => {
  return (
    roomStore.writingSubmitState || {
      required_confirmations: 3,
      confirmations: [],
      final_submitted_at: null,
    }
  )
})

const requiredConfirmations = computed(() => Number(writingState.value.required_confirmations || 3))
const confirmations = computed(() => (Array.isArray(writingState.value.confirmations) ? writingState.value.confirmations : []))
const confirmCount = computed(() => confirmations.value.length)
const isFinalSubmitted = computed(() => !!writingState.value.final_submitted_at)
const isStudent = computed(() => authStore.user?.role === 'student')
const myUserId = computed(() => String(authStore.user?.id || ''))

const isMeConfirmed = computed(() => {
  if (!myUserId.value) return false
  return confirmations.value.some((item) => String(item?.user_id || '') === myUserId.value)
})

const wordCount = computed(() => plainText.value.trim().length)

const otherEditingNames = computed(() => {
  const now = Date.now()
  return Object.values(awarenessMap.value)
    .filter((item) => item && item.user_id !== myUserId.value)
    .filter((item) => !!item.is_editing && now - Number(item.local_ts || 0) <= AWARENESS_STALE_MS)
    .map((item) => item.display_name || '同学')
})

const saveHint = computed(() => {
  if (!lastSavedAt.value) return connected.value ? '实时同步已开启' : '同步连接中...'
  return `最近同步：${lastSavedAt.value}`
})

const submitDisplay = computed(() => {
  if (!writingState.value.final_submitted_at) return ''
  const d = new Date(writingState.value.final_submitted_at)
  if (Number.isNaN(d.getTime())) return ''
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
})

const canConfirmSubmit = computed(() => {
  if (isFinalSubmitted.value) return false
  if (!isStudent.value) return false
  if (isMeConfirmed.value) return false
  return !roomStore.confirmingWritingSubmit
})

const submitButtonText = computed(() => {
  if (isFinalSubmitted.value) return `已提交 ${submitDisplay.value}`
  if (roomStore.confirmingWritingSubmit) return '确认中...'
  if (isMeConfirmed.value) return '已确认，等待他人'
  return '确认提交答题'
})

function extractPlainText(html) {
  const el = document.createElement('div')
  el.innerHTML = html || ''
  return el.textContent || ''
}

function saveDraft() {
  localStorage.setItem(storageKey.value, htmlDraft.value)
  const now = new Date()
  lastSavedAt.value = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`
}

function applyContent(content) {
  htmlDraft.value = content || ''
  plainText.value = extractPlainText(htmlDraft.value)
  if (editorRef.value && editorRef.value.innerHTML !== htmlDraft.value) {
    editorRef.value.innerHTML = htmlDraft.value
  }
  saveDraft()
}

function resetUndoHistory(content) {
  undoStack.value = [String(content || '')]
  redoStack.value = []
}

function recordUndoSnapshot(content) {
  const text = String(content || '')
  const last = undoStack.value.length ? undoStack.value[undoStack.value.length - 1] : null
  if (last === text) return
  undoStack.value.push(text)
  if (undoStack.value.length > UNDO_STACK_MAX) {
    undoStack.value = undoStack.value.slice(undoStack.value.length - UNDO_STACK_MAX)
  }
  redoStack.value = []
}

function reportWritingActivity() {
  if (!roomId) return
  const nowMs = Date.now()
  if (nowMs - lastActivityReportAt.value < ACTIVITY_REPORT_INTERVAL_MS) return
  lastActivityReportAt.value = nowMs
  roomApi.reportRoomActivity(roomId, 'writing').catch(() => {})
}

function sendAwareness(isEditing) {
  if (!roomId || !myUserId.value) return
  const nowMs = Date.now()
  if (nowMs - lastAwarenessSentAt.value < AWARENESS_SEND_INTERVAL_MS && isEditing) return
  lastAwarenessSentAt.value = nowMs
  send({
    type: 'writing:awareness',
    is_editing: !!isEditing,
    cursor: null,
  })
}

function scheduleSendUpdate() {
  if (!roomId) return
  if (wsSendTimer) {
    clearTimeout(wsSendTimer)
  }
  wsSendTimer = setTimeout(() => {
    wsSendTimer = null
    send({
      type: 'writing:update',
      content: htmlDraft.value,
      base_version: docVersion.value,
    })
  }, 120)
}

function handleInput() {
  if (!editorRef.value) return
  htmlDraft.value = editorRef.value.innerHTML
  plainText.value = editorRef.value.innerText || ''
  lastLocalEditAt.value = Date.now()
  saveDraft()
  recordUndoSnapshot(htmlDraft.value)
  reportWritingActivity()
  sendAwareness(true)
  scheduleSendUpdate()
}

function applyUndoContent(content) {
  applyContent(content)
  lastLocalEditAt.value = Date.now()
  scheduleSendUpdate()
}

function undoOnce() {
  if (undoStack.value.length <= 1) return
  const current = undoStack.value.pop()
  redoStack.value.push(current)
  const prev = undoStack.value[undoStack.value.length - 1] || ''
  applyUndoContent(prev)
}

function redoOnce() {
  if (!redoStack.value.length) return
  const next = redoStack.value.pop()
  undoStack.value.push(next)
  if (undoStack.value.length > UNDO_STACK_MAX) {
    undoStack.value = undoStack.value.slice(undoStack.value.length - UNDO_STACK_MAX)
  }
  applyUndoContent(next)
}

function handleKeydown(event) {
  const ctrlOrMeta = event.ctrlKey || event.metaKey
  if (!ctrlOrMeta) return
  const key = String(event.key || '').toLowerCase()
  if (key === 'z' && !event.shiftKey) {
    event.preventDefault()
    undoOnce()
    return
  }
  if ((key === 'z' && event.shiftKey) || key === 'y') {
    event.preventDefault()
    redoOnce()
  }
}

function handleFocus() {
  saveSelection()
  sendAwareness(true)
}

function handleBlur() {
  saveSelection()
  sendAwareness(false)
}

function focusEditor() {
  editorRef.value?.focus()
}

function saveSelection() {
  const editor = editorRef.value
  const selection = window.getSelection()
  if (!editor || !selection || selection.rangeCount === 0) return

  const range = selection.getRangeAt(0)
  if (!editor.contains(range.startContainer) || !editor.contains(range.endContainer)) return
  savedRange.value = range.cloneRange()
}

function placeCaretAtEnd() {
  const editor = editorRef.value
  if (!editor) return
  const range = document.createRange()
  range.selectNodeContents(editor)
  range.collapse(false)
  const selection = window.getSelection()
  if (!selection) return
  selection.removeAllRanges()
  selection.addRange(range)
  savedRange.value = range.cloneRange()
}

function restoreSelection() {
  const editor = editorRef.value
  if (!editor) return

  focusEditor()
  const selection = window.getSelection()
  if (!selection) return

  if (savedRange.value) {
    selection.removeAllRanges()
    selection.addRange(savedRange.value)
  } else {
    placeCaretAtEnd()
  }
}

function applyCommand(command) {
  restoreSelection()
  document.execCommand(command, false, null)
  saveSelection()
  handleInput()
}

function applyColor() {
  restoreSelection()
  const selection = window.getSelection()
  const range = selection && selection.rangeCount > 0 ? selection.getRangeAt(0) : null
  if (!range || range.collapsed) {
    return
  }

  document.execCommand('styleWithCSS', false, true)
  document.execCommand('foreColor', false, currentColor.value)
  saveSelection()
  handleInput()
}

function handleColorChange() {
  saveSelection()
}

async function confirmSubmit() {
  if (!roomId) return
  await roomStore.confirmWritingSubmit(roomId)
  reportWritingActivity()
}

async function initWritingDoc() {
  const localDraft = localStorage.getItem(storageKey.value) || ''
  try {
    const state = await roomApi.getWritingDocState(roomId)
    docVersion.value = Number(state?.version || 0)
    if (docVersion.value === 0 && localDraft) {
      applyContent(localDraft)
      resetUndoHistory(localDraft)
      scheduleSendUpdate()
    } else {
      applyContent(String(state?.content || ''))
      resetUndoHistory(String(state?.content || ''))
    }
  } catch {
    applyContent(localDraft)
    resetUndoHistory(localDraft)
  }
}

function formatWhen(isoText) {
  if (!isoText) return '--'
  const d = new Date(isoText)
  if (Number.isNaN(d.getTime())) return '--'
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}:${String(d.getSeconds()).padStart(2, '0')}`
}

async function loadHistory() {
  if (!roomId) return
  loadingHistory.value = true
  try {
    const res = await roomApi.getWritingDocHistory(roomId, { limit: 3 })
    historyItems.value = Array.isArray(res?.items) ? res.items : []
  } finally {
    loadingHistory.value = false
  }
}

async function saveVersion() {
  if (!roomId || !isStudent.value || savingVersion.value) return
  savingVersion.value = true
  try {
    const res = await roomApi.saveWritingDocVersion(roomId)
    if (historyPanelOpen.value) {
      historyItems.value = Array.isArray(res?.items) ? res.items : []
    }
  } finally {
    savingVersion.value = false
  }
}

async function toggleHistory() {
  historyPanelOpen.value = !historyPanelOpen.value
  if (historyPanelOpen.value) {
    await loadHistory()
  }
}

async function restoreVersion(version) {
  if (!roomId || !isTeacher.value) return
  if (!window.confirm(`确认回滚到 v${version} 吗？`)) return
  restoringVersion.value = version
  try {
    await roomApi.restoreWritingDocVersion(roomId, version)
    await loadHistory()
  } finally {
    restoringVersion.value = 0
  }
}

onMounted(async () => {
  if (!roomId) return

  on('writing:updated', (data) => {
    const incomingVersion = Number(data?.version || 0)
    const updatedBy = String(data?.updated_by || '')
    if (incomingVersion <= docVersion.value) return

    docVersion.value = incomingVersion

    if (updatedBy !== myUserId.value && Date.now() - lastLocalEditAt.value > 250) {
      applyContent(String(data?.content || ''))
      resetUndoHistory(String(data?.content || ''))
    }
  })

  on('writing:resync', (data) => {
    const incomingVersion = Number(data?.version || 0)
    if (incomingVersion <= docVersion.value) return
    docVersion.value = incomingVersion
    applyContent(String(data?.content || ''))
    resetUndoHistory(String(data?.content || ''))
  })

  on('writing:awareness', (data) => {
    const userId = String(data?.user_id || '')
    if (!userId) return
    awarenessMap.value = {
      ...awarenessMap.value,
      [userId]: {
        user_id: userId,
        display_name: data?.display_name || '同学',
        is_editing: !!data?.is_editing,
        local_ts: Date.now(),
      },
    }
  })

  connect()
  await initWritingDoc()
  await roomStore.loadWritingSubmitState(roomId)

  awarenessCleaner = setInterval(() => {
    const now = Date.now()
    const next = { ...awarenessMap.value }
    Object.keys(next).forEach((uid) => {
      const ts = Number(next[uid]?.local_ts || 0)
      if (!ts || now - ts > AWARENESS_STALE_MS) {
        delete next[uid]
      }
    })
    awarenessMap.value = next
  }, 2000)

  awarenessHeartbeat = setInterval(() => {
    if (document.activeElement === editorRef.value) {
      sendAwareness(true)
    }
  }, 2000)
})

onUnmounted(() => {
  sendAwareness(false)
  if (wsSendTimer) {
    clearTimeout(wsSendTimer)
    wsSendTimer = null
  }
  if (awarenessCleaner) {
    clearInterval(awarenessCleaner)
    awarenessCleaner = null
  }
  if (awarenessHeartbeat) {
    clearInterval(awarenessHeartbeat)
    awarenessHeartbeat = null
  }
  disconnect()
})

watch(editorRef, (el) => {
  if (!el) return
  el.innerHTML = htmlDraft.value || ''
})
</script>

<style scoped>
.writing-editor:empty::before {
  content: '在这里整理观点、记录结论或起草最终答案...';
  color: #9ca3af;
}
</style>
