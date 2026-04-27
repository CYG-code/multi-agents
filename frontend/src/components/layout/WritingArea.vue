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
    </div>

    <div
      ref="editorRef"
      class="writing-editor min-h-0 flex-1 overflow-auto rounded-md border border-gray-200 p-3 text-sm text-gray-700 outline-none focus:border-blue-400"
      contenteditable="true"
      @input="handleInput"
      @mouseup="saveSelection"
      @keyup="saveSelection"
      @blur="saveSelection"
      @focus="saveSelection"
    ></div>

    <div class="mt-2 flex items-center justify-between">
      <p class="text-xs text-gray-400">{{ saveHint }}</p>
      <button
        type="button"
        class="rounded-md px-3 py-1.5 text-xs text-white disabled:opacity-60"
        :class="submittedAt ? 'bg-green-600' : 'bg-blue-600 hover:bg-blue-700'"
        @click="submitAnswer"
      >
        {{ submittedAt ? `已提交 ${submittedDisplay}` : '提交答题' }}
      </button>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const editorRef = ref(null)
const htmlDraft = ref('')
const plainText = ref('')
const lastSavedAt = ref(null)
const submittedAt = ref('')
const currentColor = ref('#1f2937')
const savedRange = ref(null)

const storageKey = computed(() => {
  const roomId = String(route.params.id || '')
  return `room:${roomId}:writing_draft`
})
const submitKey = computed(() => {
  const roomId = String(route.params.id || '')
  return `room:${roomId}:writing_submitted_at`
})

const wordCount = computed(() => plainText.value.trim().length)

const saveHint = computed(() => {
  if (!lastSavedAt.value) return '自动保存已开启'
  return `已自动保存：${lastSavedAt.value}`
})

const submittedDisplay = computed(() => {
  if (!submittedAt.value) return ''
  const d = new Date(submittedAt.value)
  if (Number.isNaN(d.getTime())) return ''
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
})

function extractPlainText(html) {
  const el = document.createElement('div')
  el.innerHTML = html || ''
  return el.textContent || ''
}

function loadDraft() {
  const content = localStorage.getItem(storageKey.value)
  submittedAt.value = localStorage.getItem(submitKey.value) || ''
  htmlDraft.value = content || ''
  plainText.value = extractPlainText(htmlDraft.value)
  if (editorRef.value) {
    editorRef.value.innerHTML = htmlDraft.value
  }
}

function saveDraft() {
  localStorage.setItem(storageKey.value, htmlDraft.value)
  const now = new Date()
  lastSavedAt.value = `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`
}

function handleInput() {
  if (!editorRef.value) return
  htmlDraft.value = editorRef.value.innerHTML
  plainText.value = editorRef.value.innerText || ''
  saveDraft()
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

function submitAnswer() {
  const nowIso = new Date().toISOString()
  submittedAt.value = nowIso
  localStorage.setItem(submitKey.value, nowIso)
}

watch(storageKey, loadDraft, { immediate: true })
watch(editorRef, (el) => {
  if (!el) return
  el.innerHTML = htmlDraft.value || ''
})
</script>

<style scoped>
.writing-editor:empty::before {
  content: '在这里整理观点、记录结论或起草最终内容...';
  color: #9ca3af;
}
</style>
