# P6 阶段：UI 精修与体验优化

**所属项目：** 多智能体辅助在线协作学习平台 v1.2  
**阶段编号：** P6 / 8  
**预计周期：** 1-2 周  
**前置依赖：** P5（完整后端功能、协同分析、AI 角色体系）

---

## 一、阶段目标

在已有功能骨架基础上，按 UI 设计稿完成视觉与交互精修：接入 Tiptap + Yjs 实现讨论区/写作区协同编辑，完善聊天区展示细节，实现 @Mention 输入框，整体视觉与设计稿高度一致。

**完成标志：** 完整三栏协作界面视觉达标，讨论区/写作区支持多光标实时协同，@Mention 菜单弹出并正确触发 AI 召唤。

---

## 二、开发方案总览

```
P6 分为 5 个子模块：

  A. y-websocket 服务接入（协同编辑基础设施）
  B. Tiptap + Yjs 协同富文本编辑器（讨论区 + 写作区）
  C. @Mention 输入框（ChatInput 升级）
  D. 聊天区 UI 精修（气泡、时间线、AI 样式）
  E. 全局 UI 精修（大厅、布局、通知）
```

---

## 三、Docker Compose 扩展（接入 y-websocket）

**更新 `docker-compose.yml`：**

```yaml
services:
  # ... postgres, redis（已有）...

  y-websocket:
    image: node:18-alpine
    working_dir: /app
    command: >
      sh -c "npm install y-websocket && node /app/node_modules/.bin/y-websocket"
    environment:
      PORT: 1234
      HOST: "0.0.0.0"
    ports:
      - "1234:1234"
    restart: unless-stopped
```

> **架构说明：** y-websocket 服务与 FastAPI 聊天 WebSocket 完全独立：
> - FastAPI `ws://localhost:8000/ws/{room_id}` → 聊天消息
> - y-websocket `ws://localhost:1234` → Yjs 文档同步
>
> 前端通过不同的 Room ID 隔离讨论区与写作区：
> - 讨论区：Room ID = `discussion_{room_id}`
> - 写作区：Room ID = `writing_{room_id}`

---

## 四、详细开发步骤

### 步骤 1：安装前端协同编辑依赖

```bash
cd frontend

# Tiptap 核心
npm install @tiptap/vue-3 @tiptap/pm @tiptap/starter-kit
npm install @tiptap/extension-collaboration @tiptap/extension-collaboration-cursor

# Yjs 生态
npm install yjs y-websocket

# Tiptap 扩展（富文本格式）
npm install @tiptap/extension-bold @tiptap/extension-italic
npm install @tiptap/extension-bullet-list @tiptap/extension-ordered-list
npm install @tiptap/extension-heading @tiptap/extension-placeholder
npm install @tiptap/extension-mention  # @Mention 功能
```

---

### 步骤 2：实现 SharedYjsEditor 核心组件

**文件：** `frontend/src/components/editor/SharedYjsEditor.vue`

这是讨论区与写作区共用的协同富文本编辑器核心组件：

```vue
<script setup>
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { useEditor, EditorContent } from '@tiptap/vue-3'
import StarterKit from '@tiptap/starter-kit'
import Collaboration from '@tiptap/extension-collaboration'
import CollaborationCursor from '@tiptap/extension-collaboration-cursor'
import * as Y from 'yjs'
import { WebsocketProvider } from 'y-websocket'
import { useAuthStore } from '@/stores/auth'

const props = defineProps({
  roomId: { type: String, required: true },
  docType: {
    type: String,
    required: true,
    validator: (v) => ['discussion', 'writing'].includes(v)
  },
  placeholder: { type: String, default: '开始输入...' },
  readonly: { type: Boolean, default: false }
})

const authStore = useAuthStore()
const yjsRoomId = `yjs_room_${props.docType}_${props.roomId}`
const Y_WS_URL = import.meta.env.VITE_YJS_WS_URL || 'ws://localhost:1234'

// Yjs 文档
const ydoc = new Y.Doc()
let provider = null

// 用户光标颜色（基于用户 ID 哈希生成）
function getUserColor(userId) {
  const colors = ['#3b82f6', '#ef4444', '#10b981', '#f59e0b', '#8b5cf6']
  const index = userId.charCodeAt(0) % colors.length
  return colors[index]
}

const editor = useEditor({
  extensions: [
    StarterKit.configure({ history: false }), // Yjs 自带历史，禁用 StarterKit 的 history
    Collaboration.configure({ document: ydoc }),
    CollaborationCursor.configure({
      provider: null, // 稍后绑定
      user: {
        name: authStore.user?.display_name || '匿名',
        color: getUserColor(authStore.user?.id || '0')
      }
    })
  ],
  editable: !props.readonly,
  editorProps: {
    attributes: {
      class: 'prose prose-sm max-w-none focus:outline-none min-h-full p-3'
    }
  }
})

onMounted(() => {
  // 建立 y-websocket 连接
  provider = new WebsocketProvider(Y_WS_URL, yjsRoomId, ydoc)
  
  // 绑定 CollaborationCursor provider
  if (editor.value) {
    editor.value.commands.updateUser({
      name: authStore.user?.display_name || '匿名',
      color: getUserColor(authStore.user?.id || '0')
    })
    // 通过重新注册 extension 绑定 provider（Tiptap 官方做法）
    // 实际上通过 useEditor 的 extensions 直接配置更稳定
  }
})

onUnmounted(() => {
  provider?.destroy()
  editor.value?.destroy()
})
</script>

<template>
  <div class="flex flex-col h-full bg-white">
    <!-- 工具栏（只在写作区显示完整工具栏，讨论区精简） -->
    <div v-if="!readonly" class="flex gap-1 px-2 py-1 border-b border-gray-100 flex-shrink-0">
      <ToolbarButton
        v-for="item in toolbarItems"
        :key="item.command"
        :active="editor?.isActive(item.command)"
        :icon="item.icon"
        :title="item.title"
        @click="item.action(editor)"
      />
    </div>
    
    <!-- 协同在线用户指示 -->
    <div class="flex gap-1 px-3 py-1 text-xs text-gray-400 border-b border-gray-100 flex-shrink-0">
      <span>在线协作</span>
      <!-- Yjs awareness 显示在线用户 -->
    </div>
    
    <!-- 编辑器内容区 -->
    <div class="flex-1 overflow-y-auto">
      <EditorContent :editor="editor" class="h-full" />
    </div>
  </div>
</template>
```

---

### 步骤 3：实现讨论区组件

**文件：** `frontend/src/components/discussion/DiscussionArea.vue`

```vue
<script setup>
import { useRoute } from 'vue-router'
import SharedYjsEditor from '@/components/editor/SharedYjsEditor.vue'

const route = useRoute()
const roomId = route.params.roomId
</script>

<template>
  <div class="flex flex-col h-full">
    <!-- 区域标题栏 -->
    <div class="flex items-center justify-between px-3 py-2 bg-gray-50 border-b border-gray-200">
      <span class="text-sm font-semibold text-gray-700">① 讨论区</span>
      <span class="text-xs text-gray-400">多人实时协同编辑</span>
    </div>
    
    <!-- Yjs 协同编辑器（讨论区绑定 discussion_roomId）-->
    <SharedYjsEditor
      :room-id="roomId"
      doc-type="discussion"
      placeholder="在此梳理讨论思路与提纲..."
      class="flex-1 min-h-0"
    />
  </div>
</template>
```

---

### 步骤 4：实现写作区组件

**文件：** `frontend/src/components/writing/WritingArea.vue`

```vue
<script setup>
import { useRoute } from 'vue-router'
import SharedYjsEditor from '@/components/editor/SharedYjsEditor.vue'

const route = useRoute()
const roomId = route.params.roomId
</script>

<template>
  <div class="flex flex-col h-full">
    <!-- 区域标题栏 -->
    <div class="flex items-center justify-between px-3 py-2 bg-gray-50 border-b border-gray-200">
      <span class="text-sm font-semibold text-gray-700">② 写作区</span>
      <span class="text-xs text-gray-400">共同撰写最终答案</span>
    </div>
    
    <!-- Yjs 协同编辑器（写作区绑定 writing_roomId）-->
    <SharedYjsEditor
      :room-id="roomId"
      doc-type="writing"
      placeholder="在此共同撰写最终答案..."
      class="flex-1 min-h-0"
    />
  </div>
</template>
```

---

### 步骤 5：实现富文本工具栏组件

**文件：** `frontend/src/components/editor/EditorToolbar.vue`

```vue
<script setup>
const props = defineProps({
  editor: Object
})

const toolbarItems = [
  {
    title: '加粗',
    icon: 'B',
    bold: true,
    action: (e) => e.chain().focus().toggleBold().run(),
    isActive: (e) => e.isActive('bold')
  },
  {
    title: '斜体',
    icon: 'I',
    italic: true,
    action: (e) => e.chain().focus().toggleItalic().run(),
    isActive: (e) => e.isActive('italic')
  },
  {
    title: '无序列表',
    icon: '•—',
    action: (e) => e.chain().focus().toggleBulletList().run(),
    isActive: (e) => e.isActive('bulletList')
  },
  {
    title: '有序列表',
    icon: '1.',
    action: (e) => e.chain().focus().toggleOrderedList().run(),
    isActive: (e) => e.isActive('orderedList')
  },
  {
    title: '标题',
    icon: 'H',
    action: (e) => e.chain().focus().toggleHeading({ level: 2 }).run(),
    isActive: (e) => e.isActive('heading', { level: 2 })
  }
]
</script>

<template>
  <div class="flex gap-0.5">
    <button
      v-for="item in toolbarItems"
      :key="item.title"
      :title="item.title"
      :class="[
        'px-2 py-1 rounded text-xs font-medium transition-colors',
        item.isActive?.(editor)
          ? 'bg-blue-500 text-white'
          : 'text-gray-600 hover:bg-gray-100'
      ]"
      @click="item.action(editor)"
    >
      {{ item.icon }}
    </button>
  </div>
</template>
```

---

### 步骤 6：实现 @Mention 输入框（升级 ChatInput）

**文件：** `frontend/src/components/chat/ChatInput.vue`（全面升级）

**文件：** `frontend/src/composables/useMention.js`

```javascript
import { ref, computed } from 'vue'

const AGENT_ROLES = [
  { id: 'facilitator', label: '主持人', description: '引导讨论方向' },
  { id: 'devil_advocate', label: '批判者', description: '激发批判性思考' },
  { id: 'summarizer', label: '总结者', description: '归纳讨论要点' },
  { id: 'resource_finder', label: '资源者', description: '提供知识与数据' },
  { id: 'encourager', label: '激励者', description: '邀请参与、调节情绪' },
]

export function useMention() {
  const showMentionMenu = ref(false)
  const mentionQuery = ref('')
  const mentionIndex = ref(0)  // 当前选中项
  const mentions = ref([])     // 当前消息中的 @mentions
  
  const filteredAgents = computed(() => {
    const q = mentionQuery.value.toLowerCase()
    return AGENT_ROLES.filter(a =>
      a.label.includes(q) || a.id.includes(q)
    )
  })
  
  function checkMentionTrigger(text, cursorPos) {
    // 找到光标前最近的 @
    const beforeCursor = text.slice(0, cursorPos)
    const atIndex = beforeCursor.lastIndexOf('@')
    
    if (atIndex === -1) {
      showMentionMenu.value = false
      return
    }
    
    const query = beforeCursor.slice(atIndex + 1)
    // 只在 @ 后没有空格时显示菜单
    if (query.includes(' ')) {
      showMentionMenu.value = false
      return
    }
    
    mentionQuery.value = query
    showMentionMenu.value = true
    mentionIndex.value = 0
  }
  
  function selectAgent(agent, inputText) {
    // 替换 @query 为选中的角色标签
    const atIndex = inputText.lastIndexOf('@')
    const newText = inputText.slice(0, atIndex) + `@${agent.label} `
    
    if (!mentions.value.includes(agent.id)) {
      mentions.value.push(agent.id)
    }
    
    showMentionMenu.value = false
    mentionQuery.value = ''
    
    return newText
  }
  
  function handleArrowKey(direction) {
    if (!showMentionMenu.value) return false
    
    const max = filteredAgents.value.length - 1
    if (direction === 'up') {
      mentionIndex.value = Math.max(0, mentionIndex.value - 1)
    } else {
      mentionIndex.value = Math.min(max, mentionIndex.value + 1)
    }
    return true
  }
  
  function clearMentions() {
    mentions.value = []
  }
  
  return {
    showMentionMenu, mentionQuery, mentionIndex,
    filteredAgents, mentions,
    checkMentionTrigger, selectAgent, handleArrowKey, clearMentions
  }
}
```

**`ChatInput.vue` 升级版：**

```vue
<script setup>
import { ref, nextTick } from 'vue'
import { useMention } from '@/composables/useMention'

const emit = defineEmits(['send'])
const inputText = ref('')
const inputRef = ref(null)
const {
  showMentionMenu, filteredAgents, mentionIndex,
  mentions, checkMentionTrigger, selectAgent, handleArrowKey, clearMentions
} = useMention()

function handleInput(event) {
  const el = event.target
  checkMentionTrigger(el.value, el.selectionStart)
}

function handleKeydown(event) {
  // 方向键控制 Mention 菜单
  if (showMentionMenu.value) {
    if (event.key === 'ArrowUp') { event.preventDefault(); handleArrowKey('up'); return }
    if (event.key === 'ArrowDown') { event.preventDefault(); handleArrowKey('down'); return }
    if (event.key === 'Enter' || event.key === 'Tab') {
      event.preventDefault()
      confirmMentionSelect()
      return
    }
    if (event.key === 'Escape') {
      showMentionMenu.value = false
      return
    }
  }
  
  if (event.key === 'Enter' && !event.shiftKey && !showMentionMenu.value) {
    event.preventDefault()
    sendMessage()
  }
}

function confirmMentionSelect() {
  const agent = filteredAgents.value[mentionIndex.value]
  if (agent) {
    inputText.value = selectAgent(agent, inputText.value)
    nextTick(() => inputRef.value?.focus())
  }
}

function sendMessage() {
  const content = inputText.value.trim()
  if (!content) return
  
  // 解析消息中的 mentions（@角色名 转换为角色 ID）
  const mentionIds = parseMentionsFromText(content)
  
  emit('send', content, mentionIds)
  inputText.value = ''
  clearMentions()
}

function parseMentionsFromText(text) {
  const LABEL_TO_ID = {
    '主持人': 'facilitator',
    '批判者': 'devil_advocate',
    '总结者': 'summarizer',
    '资源者': 'resource_finder',
    '激励者': 'encourager'
  }
  
  const mentionIds = []
  const regex = /@([^\s]+)/g
  let match
  
  while ((match = regex.exec(text)) !== null) {
    const id = LABEL_TO_ID[match[1]]
    if (id && !mentionIds.includes(id)) {
      mentionIds.push(id)
    }
  }
  
  return mentionIds.slice(0, 1)  // max_mentions_per_message = 1
}
</script>

<template>
  <div class="border-t border-gray-200 bg-white">
    <!-- @Mention 菜单（浮层） -->
    <Teleport to="body">
      <Transition name="mention-menu">
        <div
          v-if="showMentionMenu && filteredAgents.length > 0"
          class="fixed z-50 bg-white border border-gray-200 rounded-xl shadow-lg
                 w-56 max-h-48 overflow-y-auto"
          style="bottom: 80px; left: 12px;"
        >
          <div class="p-1">
            <button
              v-for="(agent, idx) in filteredAgents"
              :key="agent.id"
              :class="[
                'w-full flex items-center gap-2 px-3 py-2 rounded-lg text-left text-sm',
                idx === mentionIndex
                  ? 'bg-blue-50 text-blue-700'
                  : 'hover:bg-gray-50 text-gray-700'
              ]"
              @click="() => { inputText = selectAgent(agent, inputText) }"
            >
              <span class="font-medium">{{ agent.label }}</span>
              <span class="text-xs text-gray-400">{{ agent.description }}</span>
            </button>
          </div>
        </div>
      </Transition>
    </Teleport>
    
    <!-- 输入区域 -->
    <div class="flex gap-2 items-end p-3">
      <textarea
        ref="inputRef"
        v-model="inputText"
        @input="handleInput"
        @keydown="handleKeydown"
        placeholder="输入消息，输入 @ 可召唤 AI 角色..."
        rows="2"
        class="flex-1 resize-none border border-gray-300 rounded-xl px-3 py-2
               text-sm focus:outline-none focus:border-blue-400 transition-colors"
      />
      <button
        @click="sendMessage"
        :disabled="!inputText.trim()"
        class="px-4 py-2 bg-blue-500 text-white rounded-xl text-sm font-medium
               hover:bg-blue-600 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
      >
        发送
      </button>
    </div>
  </div>
</template>
```

---

### 步骤 7：任务说明区精修

**文件：** `frontend/src/components/task/TaskRequirements.vue`

```vue
<script setup>
import { computed } from 'vue'
import { useRoomStore } from '@/stores/room'
import { marked } from 'marked'  // npm install marked

const roomStore = useRoomStore()

const renderedRequirements = computed(() => {
  const req = roomStore.currentTask?.requirements || ''
  return marked(req)
})
</script>

<template>
  <div class="flex flex-col h-full">
    <div class="px-3 py-2 bg-gray-50 border-b border-gray-200">
      <span class="text-sm font-semibold text-gray-700">④ 任务要求</span>
    </div>
    
    <div class="flex-1 overflow-y-auto p-3">
      <div
        v-if="renderedRequirements"
        class="prose prose-sm max-w-none text-gray-700"
        v-html="renderedRequirements"
      />
      <p v-else class="text-sm text-gray-400 italic">暂无任务说明</p>
    </div>
  </div>
</template>
```

**文件：** `frontend/src/components/task/TaskScript.vue`

```vue
<script setup>
import { ref, computed } from 'vue'
import { useRoomStore } from '@/stores/room'

const roomStore = useRoomStore()
const currentPhaseIndex = ref(0)

const scripts = computed(() => roomStore.currentTask?.scripts || [])
const currentScript = computed(() => scripts.value[currentPhaseIndex.value] || null)
</script>

<template>
  <div class="flex flex-col h-full">
    <div class="px-3 py-2 bg-gray-50 border-b border-gray-200">
      <span class="text-sm font-semibold text-gray-700">⑤ 任务脚本</span>
    </div>
    
    <div class="flex-1 overflow-y-auto p-3 space-y-3">
      <!-- 阶段导航 -->
      <div class="flex gap-1 overflow-x-auto pb-1">
        <button
          v-for="(script, idx) in scripts"
          :key="idx"
          :class="[
            'px-2 py-1 rounded-full text-xs whitespace-nowrap flex-shrink-0',
            idx === currentPhaseIndex
              ? 'bg-blue-500 text-white'
              : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
          ]"
          @click="currentPhaseIndex = idx"
        >
          阶段 {{ idx + 1 }}
        </button>
      </div>
      
      <!-- 当前阶段内容 -->
      <div v-if="currentScript" class="space-y-2">
        <h4 class="font-semibold text-sm text-gray-800">{{ currentScript.title }}</h4>
        <p class="text-xs text-gray-500">⏱ 预计 {{ currentScript.duration_minutes }} 分钟</p>
        <p class="text-sm text-gray-700">{{ currentScript.description }}</p>
        
        <div v-if="currentScript.hints?.length" class="space-y-1">
          <p class="text-xs font-medium text-gray-500">提示：</p>
          <ul class="space-y-0.5">
            <li
              v-for="(hint, hi) in currentScript.hints"
              :key="hi"
              class="text-xs text-gray-600 flex items-start gap-1"
            >
              <span class="text-blue-400 mt-0.5">•</span>
              {{ hint }}
            </li>
          </ul>
        </div>
      </div>
    </div>
  </div>
</template>
```

---

### 步骤 8：聊天区 UI 精修

**更新 MessageList：** 增加时间分隔线

```vue
<!-- MessageList.vue 中，相邻消息日期不同时显示分隔线 -->
<template>
  <div ref="listRef" class="p-3 space-y-1">
    <template v-for="(msg, idx) in messages" :key="msg.id">
      <!-- 日期分隔线 -->
      <div
        v-if="isDifferentDay(messages[idx-1]?.created_at, msg.created_at)"
        class="flex items-center gap-2 my-3"
      >
        <div class="flex-1 h-px bg-gray-100" />
        <span class="text-xs text-gray-400 px-2">{{ formatDate(msg.created_at) }}</span>
        <div class="flex-1 h-px bg-gray-100" />
      </div>
      
      <MessageItem :message="msg" />
    </template>
  </div>
</template>
```

**消息气泡样式总结（MessageItem.vue 最终版）：**

| 消息类型 | 气泡颜色 | 位置 | 特殊元素 |
|----------|----------|------|----------|
| 自己发送 | 蓝色 `bg-blue-500 text-white` | 右对齐 | 无 |
| 他人发送 | 白色 `bg-white border` | 左对齐 | 头像 |
| AI 主持人 | 紫色标签 + 浅灰气泡 | 左对齐（全宽） | 角色标签 |
| AI 批判者 | 红色标签 + 浅灰气泡 | 左对齐（全宽） | 角色标签 |
| AI 总结者 | 蓝色标签 + 浅灰气泡 | 左对齐（全宽） | 角色标签 |
| AI 资源者 | 绿色标签 + 浅灰气泡 | 左对齐（全宽） | 角色标签 |
| AI 激励者 | 黄色标签 + 浅灰气泡 | 左对齐（全宽） | 角色标签 |

---

### 步骤 9：大厅页面精修

**文件：** `frontend/src/views/LobbyView.vue`（精修版）

```vue
<template>
  <div class="min-h-screen bg-gray-50">
    <!-- 顶部导航 -->
    <nav class="bg-white border-b border-gray-200 px-6 py-3 flex items-center justify-between">
      <h1 class="text-lg font-bold text-gray-800">协作学习平台</h1>
      <div class="flex items-center gap-3">
        <span class="text-sm text-gray-600">{{ authStore.user?.display_name }}</span>
        <button @click="logout" class="text-sm text-gray-400 hover:text-gray-600">退出</button>
      </div>
    </nav>
    
    <!-- 主内容 -->
    <div class="max-w-4xl mx-auto px-6 py-8">
      <!-- 操作栏 -->
      <div class="flex items-center justify-between mb-6">
        <div>
          <h2 class="text-xl font-bold text-gray-800">协作房间</h2>
          <p class="text-sm text-gray-500 mt-1">选择一个房间开始协作学习</p>
        </div>
        <button
          v-if="authStore.isTeacher"
          @click="showCreateModal = true"
          class="px-4 py-2 bg-blue-500 text-white rounded-xl text-sm font-medium hover:bg-blue-600"
        >
          + 创建房间
        </button>
      </div>
      
      <!-- 状态过滤 -->
      <div class="flex gap-2 mb-4">
        <FilterTab v-for="tab in tabs" :key="tab.value" v-bind="tab"
                   :active="activeTab === tab.value"
                   @click="activeTab = tab.value" />
      </div>
      
      <!-- 房间卡片网格 -->
      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <RoomCard
          v-for="room in filteredRooms"
          :key="room.id"
          :room="room"
          @join="handleJoin(room.id)"
        />
        
        <div v-if="filteredRooms.length === 0"
             class="col-span-2 text-center py-12 text-gray-400">
          暂无{{ activeTab === 'active' ? '进行中的' : '' }}房间
        </div>
      </div>
    </div>
  </div>
</template>
```

**`RoomCard.vue` 组件：**

```vue
<template>
  <div class="bg-white rounded-2xl border border-gray-200 p-5 hover:shadow-md transition-shadow">
    <!-- 房间名 + 状态徽标 -->
    <div class="flex items-start justify-between mb-3">
      <h3 class="font-semibold text-gray-800 text-base">{{ room.name }}</h3>
      <span :class="statusBadgeClass">{{ statusLabel }}</span>
    </div>
    
    <!-- 元信息 -->
    <div class="space-y-1 mb-4">
      <p class="text-xs text-gray-400">创建时间：{{ formatTime(room.created_at) }}</p>
      <p class="text-xs text-gray-400">成员：{{ room.member_count || 0 }} 人</p>
    </div>
    
    <!-- 操作按钮 -->
    <button
      v-if="room.status !== 'ended'"
      @click="$emit('join')"
      class="w-full py-2 bg-blue-500 text-white rounded-xl text-sm font-medium hover:bg-blue-600"
    >
      进入房间
    </button>
    <p v-else class="text-center text-xs text-gray-400">已结束</p>
  </div>
</template>
```

---

### 步骤 10：全局通知（Toast）系统

**文件：** `frontend/src/components/common/ToastNotification.vue`

```vue
<script setup>
import { ref } from 'vue'

const toasts = ref([])
let nextId = 0

export function useToast() {
  function show(message, type = 'info', duration = 3000) {
    const id = ++nextId
    toasts.value.push({ id, message, type })
    setTimeout(() => {
      toasts.value = toasts.value.filter(t => t.id !== id)
    }, duration)
  }
  
  return { show }
}
</script>

<template>
  <Teleport to="body">
    <div class="fixed top-4 right-4 z-50 space-y-2">
      <Transition
        v-for="toast in toasts"
        :key="toast.id"
        name="toast"
        appear
      >
        <div :class="[
          'px-4 py-3 rounded-xl shadow-lg text-sm max-w-xs',
          toast.type === 'success' && 'bg-green-500 text-white',
          toast.type === 'error' && 'bg-red-500 text-white',
          toast.type === 'info' && 'bg-gray-800 text-white'
        ]">
          {{ toast.message }}
        </div>
      </Transition>
    </div>
  </Teleport>
</template>
```

**在 `ChatPanel.vue` 中接入 Toast：**

```javascript
const { show: showToast } = useToast()

on('room:user_join', (data) => {
  showToast(`${data.display_name} 加入了房间`, 'info')
})

on('room:user_leave', (data) => {
  showToast(`${data.display_name} 离开了房间`, 'info')
})
```

---

### 步骤 11：三栏布局最终调整

**文件：** `frontend/src/views/RoomView.vue`（最终版）

```vue
<template>
  <div class="flex h-screen overflow-hidden bg-gray-100">
    <!-- 左栏 35%：讨论区 + 写作区 上下各 50% -->
    <div class="w-[35%] flex flex-col gap-px bg-gray-200 border-r border-gray-200">
      <div class="flex-1 bg-white min-h-0 overflow-hidden">
        <DiscussionArea />
      </div>
      <div class="flex-1 bg-white min-h-0 overflow-hidden">
        <WritingArea />
      </div>
    </div>
    
    <!-- 中栏 35%：聊天区 -->
    <div class="w-[35%] flex flex-col bg-white border-r border-gray-200">
      <ChatPanel />
    </div>
    
    <!-- 右栏 30%：任务要求 + 任务脚本 上下各 50% -->
    <div class="w-[30%] flex flex-col gap-px bg-gray-200">
      <div class="flex-1 bg-white min-h-0 overflow-hidden">
        <TaskRequirements />
      </div>
      <div class="flex-1 bg-white min-h-0 overflow-hidden">
        <TaskScript />
      </div>
    </div>
  </div>
</template>
```

---

## 五、关键技术细节

### 5.1 Yjs 双区域 Room ID 隔离

```
讨论区 y-websocket Room: "yjs_room_discussion_{room_id}"
写作区 y-websocket Room: "yjs_room_writing_{room_id}"
```

两个区域共用同一个 y-websocket 服务实例，通过 Room ID 命名空间完全隔离文档内容，互不影响。

### 5.2 @Mention 解析流程

```
用户输入 "@资源者 请帮我找数据"
  ↓
parseMentionsFromText → ["resource_finder"]
  ↓
发送 WebSocket: { type: "chat:message", content: "@资源者 请帮我找数据", mentions: ["resource_finder"] }
  ↓
后端 handle_chat_message 检测 mentions 不为空
  ↓
写入 agent_queue:{room_id}（priority=0）
  ↓
AgentWorker 优先处理，resource_finder 立即响应
```

### 5.3 AI 消息气泡全宽显示

AI 角色消息（主持人、批判者等）采用全宽（不 flex 气泡对齐）展示，更接近广播式通知，与学生消息气泡的点对点样式区分。

---

## 六、演示交付物

**P6 演示版本 — 高保真界面 Demo**

**演示步骤：**
1. 进入房间，看到完整三栏布局（左 35% / 中 35% / 右 30%）
2. 在讨论区多窗口同时输入，看到多光标实时协同（Yjs）
3. 在写作区输入格式化文本（**加粗**、*斜体*、列表）
4. 聊天区发送消息，看到精致的消息气泡样式（头像/时间戳/AI 角色标签）
5. 聊天输入框输入 `@`，弹出角色选择菜单，选择「资源者」后发送
6. 资源者的回复以打字机效果出现，样式与学生消息明显区分

**验收指标：**
- [ ] 三栏宽度比例 35/35/30 正确，不溢出
- [ ] 讨论区和写作区是独立的 Yjs 文档（互不干扰）
- [ ] 多用户同时编辑讨论区，可见对方的光标（CollaborationCursor）
- [ ] @Mention 菜单正确弹出，支持键盘上下键 + Enter 选择
- [ ] 聊天区日期分隔线正确显示
- [ ] Toast 通知在用户加入/离开时正确弹出
- [ ] 刷新页面后 Yjs 文档内容保留（y-websocket 服务持久化）

---

## 七、P6 → P7 交接说明

P6 结束后：

- ✅ 完整五区三栏界面视觉达标
- ✅ Tiptap + Yjs 协同编辑正常运行（讨论区 + 写作区）
- ✅ @Mention 触发链路打通（UI → WebSocket → 后端 C 类触发）
- ✅ AI 消息样式完善（角色标签颜色、流式打字光标）

P7 阶段专注教师监控面板：Chart.js 图表、干预日志、实时数据推送展示。
