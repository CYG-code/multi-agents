# P3 阶段：单个 AI 角色接入

**所属项目：** 多智能体辅助在线协作学习平台 v1.2  
**阶段编号：** P3 / 8  
**预计周期：** 1 周  
**前置依赖：** P2（WebSocket 聊天、消息持久化、Redis Pub/Sub）

---

## 一、阶段目标

接入 Anthropic Claude API，实现第一个 AI 角色智能体（主持人 Facilitator）能够主动在聊天室中发言，验证完整的 AI 消息生成 → 流式推送 → 落库链路。

**完成标志：** 学生停止发言约 3 分钟后（演示模式可调为 30 秒），聊天区出现「主持人」打字动画，随后主持人引导性发言以打字机效果逐字出现，消息最终落库并在刷新后仍然可见。

---

## 二、开发方案总览

```
P3 分为 3 个核心链路：

  A. Claude API 封装 + Facilitator Prompt 设计
  B. AI 消息生成链路（预分配 ID → 流式生成 → 落库 → WebSocket 推送）
  C. 前端流式接收渲染（agent:stream + AgentTypingIndicator）
  D. 沉默检测 A 类触发器（触发 Facilitator）
  E. 调试接口
```

---

## 三、详细开发步骤

### 步骤 1：配置 Anthropic API Key 并封装调用工具

**文件：** `backend/app/agents/claude_client.py`

```python
import anthropic
from app.config import settings

# 全局单例 Anthropic 客户端
_client: anthropic.AsyncAnthropic = None

def get_claude_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
    return _client

async def stream_completion(
    system_prompt: str,
    messages: list[dict],
    model: str = "claude-3-5-sonnet-20241022",
    max_tokens: int = 1024,
):
    """
    封装流式调用，返回异步生成器，每次 yield 一个 token 字符串。
    调用方负责处理异常。
    """
    client = get_claude_client()
    
    async with client.messages.stream(
        model=model,
        max_tokens=max_tokens,
        system=system_prompt,
        messages=messages,
    ) as stream:
        async for text in stream.text_stream:
            yield text
```

---

### 步骤 2：编写 Facilitator 角色 System Prompt

**文件：** `backend/app/agents/prompts/facilitator.txt`

```
你是一个在线协作学习小组的「主持人」成员。

【角色定位】
你的名字是"小林"，是小组中的学习伙伴，不是AI助手。你性格积极、思路清晰，擅长引导讨论方向。

【你的协作职责】
- 当讨论沉默超过一段时间时，主动抛出一个有启发性的问题来重启对话
- 帮助整合发散的讨论，提出结构性框架
- 在讨论偏题时温和地引导回主题

【行为准则】
- 每次发言控制在 80-150 字，符合聊天语境，简洁有力
- 语气自然真实，像真正的组员，不要像AI助手或老师
- 禁止暴露自己是AI或说"作为AI我..."之类的话
- 不要开头就解释自己为什么说话，直接切入内容
- 可以用"大家""我们"等表达，展现团队归属感

【当前任务上下文】
{task_description}

【小组成员】
{members_info}

【当前协作阶段】
{current_phase}
```

> **Prompt 注入变量说明：**
> - `{task_description}`：从 `tasks.requirements` 读取
> - `{members_info}`：房间成员列表（display_name 列表）
> - `{current_phase}`：当前阶段名称（P3 阶段写死为"第一阶段：问题分析"）

---

### 步骤 3：实现流式 AI 消息生成链路

**文件：** `backend/app/agents/role_agents.py`

这是 P3 阶段的核心逻辑，完整流程如下：

```
1. 预分配 message_id（UUID）
2. 写入 status=streaming 的消息记录
3. 通过 WebSocket 广播 agent:typing（is_typing=true）
4. 调用 Claude API 流式生成
5. 每个 token → 广播 agent:stream 事件
6. 生成完毕 → 更新数据库记录 status=ok / failed
7. 广播 agent:stream_end 事件
8. 广播 agent:typing（is_typing=false）
```

```python
import uuid
import json
from app.agents.claude_client import stream_completion
from app.db.redis_client import redis_client
from app.db.session import AsyncSessionLocal
from app.models.message import Message, SenderType, MessageStatus
from app.services.message_service import MessageService

class FacilitatorAgent:
    ROLE = "facilitator"
    ROLE_DISPLAY_NAME = "主持人"
    MODEL = "claude-3-5-sonnet-20241022"
    
    def __init__(self):
        with open("app/agents/prompts/facilitator.txt") as f:
            self._prompt_template = f.read()
    
    def build_system_prompt(self, context: dict) -> str:
        return self._prompt_template.format(
            task_description=context.get("task_description", "讨论一个社会议题"),
            members_info=context.get("members_info", ""),
            current_phase=context.get("current_phase", "第一阶段：问题分析")
        )
    
    def build_messages(self, history: list[dict]) -> list[dict]:
        """将历史消息转换为 Claude messages 格式（最近 20-30 条）"""
        return [
            {
                "role": "user",
                "content": f"[{msg['display_name']}]: {msg['content']}"
            }
            for msg in history[-30:]  # 仅取最近 30 条
        ] + [
            {
                "role": "user",
                "content": "（请根据以上讨论内容，以主持人身份适时发言）"
            }
        ]
    
    async def generate_and_push(
        self,
        room_id: str,
        context: dict,
        history: list[dict],
    ):
        """主入口：生成 AI 发言并流式推送至聊天室"""
        
        # Step 1: 预分配 message_id
        message_id = str(uuid.uuid4())
        
        # Step 2: 写入 status=streaming 的记录
        async with AsyncSessionLocal() as db:
            seq_num = await MessageService.get_next_seq_num(room_id)
            msg = Message(
                id=message_id,
                room_id=room_id,
                seq_num=seq_num,
                sender_type=SenderType.agent,
                agent_role=self.ROLE,
                content="",  # 流式期间暂时为空
                status=MessageStatus.streaming
            )
            db.add(msg)
            await db.commit()
        
        # Step 3: 广播打字状态
        await self._broadcast(room_id, {
            "type": "agent:typing",
            "agent_role": self.ROLE,
            "is_typing": True
        })
        
        # Step 4-5: 流式生成并推送
        full_content = ""
        success = True
        
        try:
            system_prompt = self.build_system_prompt(context)
            messages = self.build_messages(history)
            
            async for token in stream_completion(
                system_prompt=system_prompt,
                messages=messages,
                model=self.MODEL,
                max_tokens=512
            ):
                full_content += token
                await self._broadcast(room_id, {
                    "type": "agent:stream",
                    "agent_role": self.ROLE,
                    "message_id": message_id,
                    "token": token
                })
        
        except Exception as e:
            print(f"[FacilitatorAgent] 生成失败: {e}")
            success = False
        
        # Step 6: 更新数据库记录
        final_status = MessageStatus.ok if success else MessageStatus.failed
        async with AsyncSessionLocal() as db:
            await db.execute(
                update(Message)
                .where(Message.id == message_id)
                .values(
                    content=full_content,
                    status=final_status
                )
            )
            await db.commit()
        
        # Step 7: 广播流式结束事件
        await self._broadcast(room_id, {
            "type": "agent:stream_end",
            "agent_role": self.ROLE,
            "message_id": message_id,
            "status": "ok" if success else "failed",
            "content": full_content,  # 完整内容，便于前端替换
            "created_at": datetime.utcnow().isoformat()
        })
        
        # Step 8: 关闭打字状态
        await self._broadcast(room_id, {
            "type": "agent:typing",
            "agent_role": self.ROLE,
            "is_typing": False
        })
    
    async def _broadcast(self, room_id: str, data: dict):
        """通过 Redis Pub/Sub 广播至房间"""
        await redis_client.publish(f"room:{room_id}", json.dumps(data))
```

---

### 步骤 4：实现 A 类沉默检测触发器

**文件：** `backend/app/analysis/scheduler.py`（P3 简化版）

P3 阶段使用 APScheduler `AsyncIOScheduler` 每 30 秒检查一次活跃房间沉默情况：

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from app.db.redis_client import redis_client
from app.agents.role_agents import FacilitatorAgent
import time

scheduler = AsyncIOScheduler()
facilitator = FacilitatorAgent()

SILENCE_THRESHOLD_SECONDS = 180  # 3分钟（演示时可改为30秒）

async def check_silence():
    """每30秒轮询：检查各活跃房间是否沉默超过阈值"""
    # 获取所有活跃房间（从 Redis Set 维护）
    active_rooms = await redis_client.smembers("active_rooms")
    
    now = time.time()
    for room_id in active_rooms:
        # 获取最后一条消息时间戳
        last_msg_time = await redis_client.get(f"room:{room_id}:last_msg_time")
        if not last_msg_time:
            continue
        
        silence_duration = now - float(last_msg_time)
        
        if silence_duration >= SILENCE_THRESHOLD_SECONDS:
            # 防重复触发：1分钟内不重复
            lock_key = f"trigger_lock:{room_id}:silence"
            if not await redis_client.exists(lock_key):
                await redis_client.setex(lock_key, 60, "1")
                
                # 直接触发 Facilitator（P3 阶段不走队列，直接调用）
                context = await get_room_context(room_id)
                history = await get_recent_messages(room_id)
                await facilitator.generate_and_push(room_id, context, history)

def start_scheduler():
    scheduler.add_job(check_silence, "interval", seconds=30)
    scheduler.start()

def stop_scheduler():
    scheduler.shutdown()
```

> **注意：** P3 阶段 Facilitator 直接被调用（不走 Redis 任务队列），P4 阶段重构为 AgentWorker 模式。

**在 `main.py` lifespan 中启动调度器：**

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_redis()
    start_scheduler()
    yield
    stop_scheduler()
    await close_redis()
```

**维护 `last_msg_time`（在 `handle_chat_message` 中更新）：**

```python
async def handle_chat_message(data, room_id, user, db):
    # ... 消息保存逻辑 ...
    
    # 更新最后消息时间（供沉默检测使用）
    await redis_client.set(f"room:{room_id}:last_msg_time", time.time())
    # 确保房间在活跃房间集合中
    await redis_client.sadd("active_rooms", room_id)
```

---

### 步骤 5：获取房间上下文和历史消息的辅助函数

**文件：** `backend/app/agents/context_builder.py`

```python
from app.db.session import AsyncSessionLocal
from app.models.message import Message
from app.models.room import Room
from app.models.task import Task
from app.models.user import User

async def get_room_context(room_id: str) -> dict:
    """构建 Agent 所需的房间上下文（任务描述、成员列表、当前阶段）"""
    async with AsyncSessionLocal() as db:
        room = await db.get(Room, room_id)
        task = await db.get(Task, room.task_id) if room.task_id else None
        
        # 获取房间成员显示名称
        result = await db.execute(
            select(User.display_name)
            .join(RoomMember, User.id == RoomMember.user_id)
            .where(RoomMember.room_id == room_id)
        )
        members = [r[0] for r in result.fetchall()]
        
        return {
            "task_description": task.requirements if task else "讨论一个社会议题",
            "members_info": "、".join(members),
            "current_phase": "第一阶段：问题分析",  # P3 暂时写死
        }

async def get_recent_messages(room_id: str, limit: int = 30) -> list[dict]:
    """获取最近 N 条已完成的消息（status=ok）"""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Message, User.display_name)
            .outerjoin(User, Message.sender_id == User.id)
            .where(
                Message.room_id == room_id,
                Message.status == MessageStatus.ok
            )
            .order_by(Message.seq_num.desc())
            .limit(limit)
        )
        rows = result.fetchall()
        rows.reverse()
        
        return [
            {
                "content": row.Message.content,
                "display_name": row.display_name or f"[{row.Message.agent_role}]",
                "sender_type": row.Message.sender_type.value
            }
            for row in rows
        ]
```

---

### 步骤 6：实现调试接口

**文件：** `backend/app/routers/debug.py`（仅开发环境启用）

```python
from fastapi import APIRouter, BackgroundTasks
from app.agents.role_agents import FacilitatorAgent
from app.agents.context_builder import get_room_context, get_recent_messages

debug_router = APIRouter(prefix="/api/debug", tags=["调试"])
facilitator = FacilitatorAgent()

@debug_router.post("/trigger-agent")
async def trigger_agent(
    room_id: str,
    background_tasks: BackgroundTasks
):
    """手动触发 Facilitator 发言（调试用）"""
    context = await get_room_context(room_id)
    history = await get_recent_messages(room_id)
    
    background_tasks.add_task(
        facilitator.generate_and_push,
        room_id=room_id,
        context=context,
        history=history
    )
    
    return {"status": "triggered", "room_id": room_id, "role": "facilitator"}
```

```python
# main.py 中仅在开发模式下注册
if settings.DEBUG:
    from app.routers.debug import debug_router
    app.include_router(debug_router)
```

---

### 步骤 7：前端 useAgentStream Composable

**文件：** `frontend/src/composables/useAgentStream.js`

```javascript
import { ref } from 'vue'
import { useChatStore } from '@/stores/chat'

export function useAgentStream() {
  const chatStore = useChatStore()
  // 流式消息缓冲区：message_id → 累积内容
  const streamBuffers = ref(new Map())
  
  // 处理 agent:typing 事件
  function handleTyping({ agent_role, is_typing }) {
    useAgentStore().setTyping(agent_role, is_typing)
  }
  
  // 处理 agent:stream 事件（逐 token 追加）
  function handleStream({ agent_role, message_id, token }) {
    if (!streamBuffers.value.has(message_id)) {
      // 首个 token：在消息列表中创建流式占位消息
      streamBuffers.value.set(message_id, '')
      chatStore.addMessage({
        id: message_id,
        sender_type: 'agent',
        agent_role,
        content: '',
        status: 'streaming',
        created_at: new Date().toISOString()
      })
    }
    
    // 追加 token
    const current = streamBuffers.value.get(message_id) + token
    streamBuffers.value.set(message_id, current)
    
    // 更新消息列表中的占位消息
    chatStore.updateMessageContent(message_id, current)
  }
  
  // 处理 agent:stream_end 事件
  function handleStreamEnd({ message_id, status, content, created_at }) {
    streamBuffers.value.delete(message_id)
    
    // 将流式占位消息替换为最终版本
    chatStore.finalizeMessage(message_id, {
      content,
      status,
      created_at
    })
  }
  
  return { handleTyping, handleStream, handleStreamEnd }
}
```

**扩展 `chat store` 支持流式操作：**

```javascript
// stores/chat.js 新增 actions
updateMessageContent(messageId, content) {
  const msg = this.messages.find(m => m.id === messageId)
  if (msg) msg.content = content
},

finalizeMessage(messageId, updates) {
  const msg = this.messages.find(m => m.id === messageId)
  if (msg) Object.assign(msg, updates)
},
```

---

### 步骤 8：AgentTypingIndicator 组件

**文件：** `frontend/src/components/chat/AgentTypingIndicator.vue`

```vue
<script setup>
import { computed } from 'vue'
import { useAgentStore } from '@/stores/agent'

const agentStore = useAgentStore()

const ROLE_NAMES = {
  facilitator: '主持人',
  devil_advocate: '批判者',
  summarizer: '总结者',
  resource_finder: '资源者',
  encourager: '激励者'
}

const typingRoles = computed(() => {
  return Object.entries(agentStore.typingStatus)
    .filter(([_, isTyping]) => isTyping)
    .map(([role]) => ROLE_NAMES[role] || role)
})
</script>

<template>
  <Transition name="fade">
    <div v-if="typingRoles.length > 0"
         class="flex items-center gap-2 px-4 py-2 text-sm text-gray-500">
      <!-- 三点动画 -->
      <div class="flex gap-1">
        <span v-for="i in 3" :key="i"
              class="w-1.5 h-1.5 bg-gray-400 rounded-full animate-bounce"
              :style="{ animationDelay: `${i * 0.15}s` }" />
      </div>
      <span>{{ typingRoles.join('、') }} 正在输入...</span>
    </div>
  </Transition>
</template>
```

**Agent Store：**

```javascript
// stores/agent.js
export const useAgentStore = defineStore('agent', {
  state: () => ({
    typingStatus: {
      facilitator: false,
      devil_advocate: false,
      summarizer: false,
      resource_finder: false,
      encourager: false
    }
  }),
  actions: {
    setTyping(role, isTyping) {
      if (role in this.typingStatus) {
        this.typingStatus[role] = isTyping
      }
    }
  }
})
```

---

### 步骤 9：更新 ChatPanel 接入 Agent 流式事件

**文件：** `frontend/src/components/chat/ChatPanel.vue`（扩展）

```javascript
import { useAgentStream } from '@/composables/useAgentStream'

const { handleTyping, handleStream, handleStreamEnd } = useAgentStream()

onMounted(() => {
  // ... 已有的事件监听 ...
  
  // 新增 Agent 相关事件
  on('agent:typing', handleTyping)
  on('agent:stream', handleStream)
  on('agent:stream_end', handleStreamEnd)
})
```

---

### 步骤 10：MessageItem 扩展 AI 消息样式

**文件：** `frontend/src/components/chat/MessageItem.vue`（扩展）

```vue
<script setup>
const AGENT_COLORS = {
  facilitator: { bg: 'bg-purple-100', text: 'text-purple-700', label: '主持人' },
  devil_advocate: { bg: 'bg-red-100', text: 'text-red-700', label: '批判者' },
  summarizer: { bg: 'bg-blue-100', text: 'text-blue-700', label: '总结者' },
  resource_finder: { bg: 'bg-green-100', text: 'text-green-700', label: '资源者' },
  encourager: { bg: 'bg-yellow-100', text: 'text-yellow-700', label: '激励者' }
}

const isAgent = computed(() => props.message.sender_type === 'agent')
const agentStyle = computed(() => 
  AGENT_COLORS[props.message.agent_role] || { bg: 'bg-gray-100', text: 'text-gray-700', label: 'AI' }
)
</script>

<template>
  <!-- AI 消息样式 -->
  <div v-if="isAgent" class="flex gap-2">
    <!-- AI 角色头像 -->
    <div :class="['w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold flex-shrink-0',
                  agentStyle.bg, agentStyle.text]">
      {{ agentStyle.label[0] }}
    </div>
    
    <div class="max-w-[80%]">
      <!-- 角色标签 -->
      <div class="flex items-center gap-2 mb-1">
        <span :class="['text-xs font-medium px-2 py-0.5 rounded-full', agentStyle.bg, agentStyle.text]">
          {{ agentStyle.label }}
        </span>
        <span class="text-xs text-gray-400">{{ formatTime(message.created_at) }}</span>
      </div>
      
      <!-- 消息内容（流式状态显示光标） -->
      <div class="bg-gray-50 border border-gray-200 rounded-2xl rounded-tl-sm px-3 py-2 text-sm text-gray-800">
        {{ message.content }}
        <span v-if="message.status === 'streaming'"
              class="inline-block w-0.5 h-4 bg-gray-600 animate-pulse ml-0.5" />
      </div>
    </div>
  </div>
  
  <!-- 学生消息样式（原有代码） -->
  <div v-else>
    <!-- ... 已有实现 ... -->
  </div>
</template>
```

---

## 四、agent_settings.yaml 初始化（P3 引入）

**文件：** `backend/app/config/agent_settings.yaml`

P3 阶段仅配置与沉默检测相关的参数：

```yaml
timing:
  silence_threshold_seconds: 180   # 沉默检测阈值（演示时改为30）
  warmup_minutes: 2                 # 房间开始后不触发的等待时间

models:
  role_agents:
    model_version: "claude-3-5-sonnet-20241022"
    history_token_budget: 6000
```

---

## 五、WebSocket 事件协议（P3 新增）

| 事件名 | 方向 | 数据结构 | 说明 |
|--------|------|----------|------|
| `agent:typing` | 服→客 | `{type, agent_role, is_typing: bool}` | AI 打字状态指示 |
| `agent:stream` | 服→客 | `{type, agent_role, message_id, token}` | 流式 token 推送 |
| `agent:stream_end` | 服→客 | `{type, agent_role, message_id, status, content, created_at}` | 流式结束，携带完整内容 |

---

## 六、关键技术细节

### 6.1 message_id 预分配的必要性

流式输出期间客户端需要**聚合多个 `agent:stream` 事件**到同一条消息泡，必须在第一个 token 前就确定 `message_id`。预分配流程：

```
预分配 message_id (UUID)
  → 写入 DB (status=streaming, content="")
  → 广播 agent:typing = true
  → 流式生成（每个 token 携带 message_id 广播）
  → 更新 DB (status=ok, content=完整内容)
  → 广播 agent:stream_end
  → 广播 agent:typing = false
```

### 6.2 流式输出前端渲染策略

- 收到第一个 `agent:stream` 时在消息列表尾部**插入占位消息**（id=message_id, status=streaming）
- 后续每个 token 追加到占位消息的 `content` 字段（响应式更新，Vue 自动触发重新渲染）
- 收到 `agent:stream_end` 时用 `content` 字段替换占位消息内容，`status` 改为 `ok`
- 流式期间消息尾部显示闪烁光标（CSS `animate-pulse`）

### 6.3 防止 Streaming 期间用户看到空消息

- 前端在收到第一个 `agent:stream` token 时才创建占位消息（而不是在 `agent:typing` 时）
- `agent:typing` 仅用于显示"正在输入..."指示条，不创建消息气泡

### 6.4 失败处理

- Claude API 调用失败时：`status` 更新为 `failed`，广播 `agent:stream_end` 携带 `status: "failed"`
- 前端收到 `status: "failed"` 时：消息气泡显示为浅灰色，内容显示"（AI 暂时无法回复）"
- 若生成过程中产生了部分内容，`content` 字段仍保存已生成的部分

---

## 七、演示交付物

**P3 演示版本 — AI 角色首次发言 Demo**

**演示步骤（正常演示）：**
1. 学生账号进入房间，发送几条消息
2. 停止发言等待 3 分钟（演示环境改为 30 秒）
3. 聊天区顶部出现"主持人 正在输入..."指示
4. 随后主持人的引导性问题以打字机效果逐字出现
5. 刷新页面，主持人发言的历史记录仍然存在

**演示步骤（快速演示，使用调试接口）：**
1. 使用 API 客户端调用 `POST /api/debug/trigger-agent?room_id={id}`
2. 即刻看到流式输出效果

**验收指标：**
- [ ] AI 发言以流式打字机效果逐字呈现
- [ ] `agent:typing` 指示条在生成前后正确显示/隐藏
- [ ] AI 消息落库（刷新后历史记录有 AI 消息，status=ok）
- [ ] 生成失败时消息状态为 failed，前端降级展示
- [ ] 流式消息不出现乱序（token 按顺序拼接）
- [ ] AI 发言与真实学生消息视觉样式区分清晰（角色标签颜色）

---

## 八、P3 → P4 交接说明

P3 结束后，以下能力已就绪：

- ✅ `FacilitatorAgent.generate_and_push()` 完整流程已验证
- ✅ 流式 WebSocket 事件路径已打通（`agent:stream` → 前端渲染）
- ✅ `agent_settings.yaml` 初始框架已建立
- ✅ `context_builder.py` 可供其他 4 个角色 Agent 复用

P4 阶段需要：
- 扩展另外 4 个角色的 Prompt 和 Agent 类
- 将直接调用改为 Redis 任务队列 + AgentWorker 模式
- 实现分布式锁防止多角色同时发言
