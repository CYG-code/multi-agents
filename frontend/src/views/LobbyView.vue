<template>
  <div class="min-h-screen bg-gray-100">
    <!-- 顶栏 -->
    <header class="bg-white shadow-sm px-6 py-4 flex justify-between items-center">
      <h1 class="text-lg font-bold text-gray-800">协作学习平台 — 大厅</h1>
      <div class="flex items-center gap-4">
        <span class="text-sm text-gray-600">{{ authStore.user?.display_name }}（{{ authStore.isTeacher ? '教师' : '学生' }}）</span>
        <button @click="authStore.logout(); router.push('/login')"
          class="text-sm text-red-500 hover:underline">退出</button>
      </div>
    </header>

    <main class="max-w-4xl mx-auto px-6 py-8">
      <!-- 教师：创建房间 -->
      <div v-if="authStore.isTeacher" class="mb-6 flex justify-end">
        <button @click="showModal = true"
          class="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700">
          + 创建房间
        </button>
      </div>

      <!-- 房间列表 -->
      <div v-if="rooms.length === 0" class="text-center text-gray-400 py-16">暂无房间</div>
      <div class="grid grid-cols-1 gap-4">
        <div v-for="room in rooms" :key="room.id"
          class="bg-white rounded-xl shadow-sm p-5 flex justify-between items-center">
          <div>
            <p class="font-medium text-gray-800">{{ room.name }}</p>
            <div class="flex items-center gap-2 mt-1">
              <span class="text-xs px-2 py-0.5 rounded-full"
                :class="room.status === 'active' ? 'bg-green-100 text-green-700' : 'bg-yellow-100 text-yellow-700'">
                {{ room.status === 'active' ? '进行中' : '等待中' }}
              </span>
              <span class="text-xs text-gray-400">{{ room.member_count }} 人</span>
            </div>
          </div>
          <button @click="joinRoom(room.id)"
            class="bg-blue-600 text-white px-4 py-2 rounded-lg text-sm hover:bg-blue-700">
            加入
          </button>
        </div>
      </div>
    </main>

    <!-- 创建房间 Modal -->
    <div v-if="showModal" class="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
      <div class="bg-white rounded-xl p-6 w-full max-w-sm shadow-xl">
        <h2 class="text-lg font-bold mb-4">创建房间</h2>
        <form @submit.prevent="handleCreateRoom" class="space-y-4">
          <div>
            <label class="block text-sm font-medium text-gray-700 mb-1">房间名称</label>
            <input v-model="newRoomName" type="text" required
              class="w-full border border-gray-300 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500" />
          </div>
          <p v-if="createError" class="text-red-500 text-sm">{{ createError }}</p>
          <div class="flex gap-3">
            <button type="button" @click="showModal = false"
              class="flex-1 border border-gray-300 py-2 rounded-lg text-sm hover:bg-gray-50">取消</button>
            <button type="submit" :disabled="creating"
              class="flex-1 bg-blue-600 text-white py-2 rounded-lg text-sm hover:bg-blue-700 disabled:opacity-50">
              {{ creating ? '创建中...' : '确认创建' }}
            </button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth.js'
import api from '../services/api.js'

const router = useRouter()
const authStore = useAuthStore()

const rooms = ref([])
const showModal = ref(false)
const newRoomName = ref('')
const creating = ref(false)
const createError = ref('')

onMounted(fetchRooms)

async function fetchRooms() {
  rooms.value = await api.get('/rooms')
}

async function joinRoom(roomId) {
  await api.post(`/rooms/${roomId}/join`)
  router.push(`/room/${roomId}`)
}

async function handleCreateRoom() {
  createError.value = ''
  creating.value = true
  try {
    await api.post('/rooms', { name: newRoomName.value })
    showModal.value = false
    newRoomName.value = ''
    await fetchRooms()
  } catch (e) {
    createError.value = e.response?.data?.detail || '创建失败'
  } finally {
    creating.value = false
  }
}
</script>
