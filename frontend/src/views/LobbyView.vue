<template>
  <div class="min-h-screen bg-gray-100">
    <header class="flex items-center justify-between bg-white px-6 py-4 shadow-sm">
      <h1 class="text-lg font-bold text-gray-800">协作学习平台 - 大厅</h1>
      <div class="flex items-center gap-4">
        <span class="text-sm text-gray-600">
          {{ authStore.user?.display_name }}（{{ authStore.isTeacher ? '教师' : '学生' }}）
        </span>
        <button class="text-sm text-red-500 hover:underline" @click="authStore.logout(); router.push('/login')">
          退出
        </button>
      </div>
    </header>

    <main class="mx-auto max-w-4xl px-6 py-8">
      <div v-if="authStore.isTeacher" class="mb-6 flex justify-end gap-3">
        <button class="rounded-lg border border-blue-200 bg-white px-4 py-2 text-blue-700 hover:bg-blue-50" @click="openTemplateModal">
          + 创建模板
        </button>
        <button class="rounded-lg bg-blue-600 px-4 py-2 text-white hover:bg-blue-700" @click="openCreateModal">
          + 创建房间
        </button>
      </div>

      <div v-if="rooms.length === 0" class="py-16 text-center text-gray-400">暂无房间</div>
      <div class="grid grid-cols-1 gap-4">
        <div
          v-for="room in rooms"
          :key="room.id"
          class="flex items-center justify-between rounded-xl bg-white p-5 shadow-sm"
        >
          <div>
            <p class="font-medium text-gray-800">{{ room.name }}</p>
            <div class="mt-1 flex items-center gap-2">
              <span
                class="rounded-full px-2 py-0.5 text-xs"
                :class="room.status === 'active' ? 'bg-green-100 text-green-700' : 'bg-yellow-100 text-yellow-700'"
              >
                {{ room.status === 'active' ? '进行中' : '等待中' }}
              </span>
              <span class="text-xs text-gray-400">{{ room.member_count }} 人</span>
            </div>
          </div>

          <div class="flex items-center gap-2">
            <button class="rounded-lg bg-blue-600 px-4 py-2 text-sm text-white hover:bg-blue-700" @click="joinRoom(room.id)">
              加入
            </button>
            <button
              v-if="authStore.isTeacher"
              class="rounded-lg border border-red-300 px-4 py-2 text-sm text-red-600 hover:bg-red-50"
              @click="openDeleteModal(room)"
            >
              删除
            </button>
          </div>
        </div>
      </div>
    </main>

    <div v-if="showModal" class="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div class="w-full max-w-xl rounded-xl bg-white p-6 shadow-xl">
        <h2 class="mb-4 text-lg font-bold">创建房间</h2>
        <form class="space-y-4" @submit.prevent="handleCreateRoom">
          <div>
            <label class="mb-1 block text-sm font-medium text-gray-700">房间名称</label>
            <input
              v-model="newRoomName"
              type="text"
              required
              class="w-full rounded-lg border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
          <div>
            <label class="mb-1 block text-sm font-medium text-gray-700">创建方式</label>
            <div class="flex gap-3 rounded-lg border border-gray-200 p-2">
              <label class="inline-flex items-center gap-2 text-sm text-gray-700">
                <input v-model="createMode" type="radio" value="template" />
                使用模板
              </label>
              <label class="inline-flex items-center gap-2 text-sm text-gray-700">
                <input v-model="createMode" type="radio" value="manual" />
                手动输入
              </label>
            </div>
          </div>

          <div v-if="createMode === 'template'">
            <label class="mb-1 block text-sm font-medium text-gray-700">选择模板</label>
            <select
              v-model="selectedTemplateId"
              class="w-full rounded-lg border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="" disabled>{{ templatesLoading ? '模板加载中...' : '请选择模板' }}</option>
              <option v-for="item in templates" :key="item.id" :value="item.id">
                {{ item.title || '未命名模板' }}
              </option>
            </select>
            <p v-if="!templatesLoading && templates.length === 0" class="mt-1 text-xs text-amber-600">
              暂无可用模板，请切换到“手动输入”
            </p>
          </div>

          <div v-if="createMode === 'template' && selectedTemplate">
            <label class="mb-1 block text-sm font-medium text-gray-700">模板预览：任务要求</label>
            <textarea
              :value="selectedTemplate.requirements || '暂无任务要求'"
              rows="3"
              disabled
              class="w-full resize-none rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 text-gray-600"
            />
          </div>

          <div v-if="createMode === 'manual'">
            <label class="mb-1 block text-sm font-medium text-gray-700">任务标题</label>
            <input
              v-model="taskTitle"
              type="text"
              placeholder="默认使用房间名"
              class="w-full rounded-lg border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
          <div v-if="createMode === 'manual'">
            <label class="mb-1 block text-sm font-medium text-gray-700">任务要求</label>
            <textarea
              v-model="taskRequirements"
              rows="4"
              required
              placeholder="请输入任务要求..."
              class="w-full rounded-lg border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
          <p v-if="createError" class="text-sm text-red-500">{{ createError }}</p>
          <div class="flex gap-3">
            <button
              type="button"
              class="flex-1 rounded-lg border border-gray-300 py-2 text-sm hover:bg-gray-50"
              @click="closeCreateModal"
            >
              取消
            </button>
            <button
              type="submit"
              :disabled="creating"
              class="flex-1 rounded-lg bg-blue-600 py-2 text-sm text-white hover:bg-blue-700 disabled:opacity-50"
            >
              {{ creating ? '创建中...' : '确认创建' }}
            </button>
          </div>
        </form>
      </div>
    </div>

    <div v-if="showDeleteModal" class="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div class="w-full max-w-md rounded-xl bg-white p-6 shadow-xl">
        <h2 class="mb-3 text-lg font-bold text-gray-800">删除房间确认</h2>
        <p class="mb-2 text-sm text-gray-600">
          请输入房间名称以确认删除：
          <span class="font-semibold text-gray-900">{{ deletingRoom?.name }}</span>
        </p>
        <input
          v-model="deleteConfirmName"
          type="text"
          class="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-red-400"
          placeholder="输入房间名称"
        />
        <p v-if="deleteError" class="mt-2 text-sm text-red-500">{{ deleteError }}</p>
        <div class="mt-4 flex gap-3">
          <button
            type="button"
            class="flex-1 rounded-lg border border-gray-300 py-2 text-sm hover:bg-gray-50"
            @click="closeDeleteModal"
          >
            取消
          </button>
          <button
            type="button"
            :disabled="!canDelete || deleting"
            class="flex-1 rounded-lg bg-red-600 py-2 text-sm text-white hover:bg-red-700 disabled:opacity-50"
            @click="confirmDeleteRoom"
          >
            {{ deleting ? '删除中...' : '确认删除' }}
          </button>
        </div>
      </div>
    </div>

    <div v-if="showTemplateModal" class="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div class="w-full max-w-xl rounded-xl bg-white p-6 shadow-xl">
        <h2 class="mb-4 text-lg font-bold">创建模板</h2>
        <form class="space-y-4" @submit.prevent="handleCreateTemplate">
          <div>
            <label class="mb-1 block text-sm font-medium text-gray-700">模板标题</label>
            <input
              v-model="templateTitle"
              type="text"
              required
              class="w-full rounded-lg border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
              placeholder="请输入模板标题"
            />
          </div>
          <div>
            <label class="mb-1 block text-sm font-medium text-gray-700">任务要求</label>
            <textarea
              v-model="templateRequirements"
              rows="4"
              required
              class="w-full rounded-lg border border-gray-300 px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
              placeholder="请输入任务要求..."
            />
          </div>
          <p v-if="templateError" class="text-sm text-red-500">{{ templateError }}</p>
          <div class="flex gap-3">
            <button
              type="button"
              class="flex-1 rounded-lg border border-gray-300 py-2 text-sm hover:bg-gray-50"
              @click="closeTemplateModal"
            >
              取消
            </button>
            <button
              type="submit"
              :disabled="templateCreating"
              class="flex-1 rounded-lg bg-blue-600 py-2 text-sm text-white hover:bg-blue-700 disabled:opacity-50"
            >
              {{ templateCreating ? '保存中...' : '保存模板' }}
            </button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth.js'
import api from '../services/api.js'

const router = useRouter()
const authStore = useAuthStore()

const rooms = ref([])
const showModal = ref(false)
const newRoomName = ref('')
const createMode = ref('template')
const templates = ref([])
const templatesLoading = ref(false)
const selectedTemplateId = ref('')
const taskTitle = ref('')
const taskRequirements = ref('')
const creating = ref(false)
const createError = ref('')

const showDeleteModal = ref(false)
const deletingRoom = ref(null)
const deleteConfirmName = ref('')
const deleteError = ref('')
const deleting = ref(false)
const showTemplateModal = ref(false)
const templateTitle = ref('')
const templateRequirements = ref('')
const templateCreating = ref(false)
const templateError = ref('')

const canDelete = computed(() => {
  return !!deletingRoom.value && deleteConfirmName.value.trim() === deletingRoom.value.name
})
const selectedTemplate = computed(() => {
  if (!selectedTemplateId.value) return null
  return templates.value.find((t) => t.id === selectedTemplateId.value) || null
})

onMounted(fetchRooms)

async function fetchRooms() {
  rooms.value = await api.get('/rooms')
}

async function joinRoom(roomId) {
  await api.post(`/rooms/${roomId}/join`)
  router.push(`/room/${roomId}`)
}

function closeCreateModal() {
  showModal.value = false
  createError.value = ''
}

function openTemplateModal() {
  showTemplateModal.value = true
  templateError.value = ''
  templateTitle.value = ''
  templateRequirements.value = ''
}

function closeTemplateModal() {
  showTemplateModal.value = false
  templateError.value = ''
}

async function openCreateModal() {
  showModal.value = true
  createError.value = ''
  createMode.value = 'template'
  selectedTemplateId.value = ''
  await loadTemplates()
  if (!templates.value.length) {
    createMode.value = 'manual'
  }
}

async function loadTemplates() {
  templatesLoading.value = true
  try {
    const data = await api.get('/tasks')
    templates.value = Array.isArray(data) ? data : []
  } catch {
    templates.value = []
  } finally {
    templatesLoading.value = false
  }
}

async function handleCreateRoom() {
  createError.value = ''
  creating.value = true
  try {
    if (!newRoomName.value.trim()) {
      createError.value = '房间名称不能为空'
      return
    }

    let taskId = null
    if (createMode.value === 'template') {
      if (!selectedTemplate.value) {
        createError.value = '请选择一个模板'
        return
      }
      taskId = selectedTemplate.value.id
    } else {
      if (!taskRequirements.value.trim()) {
        createError.value = '任务要求为必填项'
        return
      }

      const createdTask = await api.post('/tasks', {
        title: taskTitle.value.trim() || `${newRoomName.value.trim()} - 任务`,
        requirements: taskRequirements.value.trim(),
      })
      taskId = createdTask.id
    }

    await api.post('/rooms', { name: newRoomName.value.trim(), task_id: taskId })

    showModal.value = false
    newRoomName.value = ''
    selectedTemplateId.value = ''
    taskTitle.value = ''
    taskRequirements.value = ''
    await fetchRooms()
  } catch (e) {
    createError.value = e.response?.data?.detail || '创建失败'
  } finally {
    creating.value = false
  }
}

function openDeleteModal(room) {
  deletingRoom.value = room
  deleteConfirmName.value = ''
  deleteError.value = ''
  showDeleteModal.value = true
}

function closeDeleteModal() {
  showDeleteModal.value = false
  deletingRoom.value = null
  deleteConfirmName.value = ''
  deleteError.value = ''
}

async function confirmDeleteRoom() {
  if (!deletingRoom.value) return
  if (!canDelete.value) {
    deleteError.value = '请输入正确的房间名称'
    return
  }

  deleting.value = true
  deleteError.value = ''
  try {
    await api.delete(`/rooms/${deletingRoom.value.id}`, {
      data: {
        confirm_name: deleteConfirmName.value.trim(),
      },
    })
    closeDeleteModal()
    await fetchRooms()
  } catch (e) {
    deleteError.value = e.response?.data?.detail || '删除失败'
  } finally {
    deleting.value = false
  }
}

async function handleCreateTemplate() {
  templateError.value = ''
  templateCreating.value = true
  try {
    if (!templateTitle.value.trim()) {
      templateError.value = '模板标题不能为空'
      return
    }
    if (!templateRequirements.value.trim()) {
      templateError.value = '任务要求为必填项'
      return
    }

    const created = await api.post('/tasks', {
      title: templateTitle.value.trim(),
      requirements: templateRequirements.value.trim(),
    })

    await loadTemplates()
    selectedTemplateId.value = created?.id || ''
    closeTemplateModal()
  } catch (e) {
    templateError.value = e.response?.data?.detail || '模板创建失败'
  } finally {
    templateCreating.value = false
  }
}
</script>
