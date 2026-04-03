# 多智能体辅助在线协作学习平台

**系统开发文档 v1.2**

*Multi-Agent Collaborative Learning Platform*

**技术栈：** Vue 3 + Python FastAPI + PostgreSQL + Redis + Anthropic Claude API

**文档状态：** 修订稿 v1.2 | **适用阶段：** 全周期开发参考

> 相较 v1.1 的主要变更：① 幕后分析层重构为专家委员会多智能体架构；② 废除讨论区编辑锁，全站统一 Yjs 协同；③ 新增 @Agent 主动召唤机制；④ 引入集中化 AI 微调配置文件 `agent_settings.yaml`

---

## 目录

1. [项目概述](#1-项目概述)
2. [UI 设计解析与前端结构](#2-ui-设计解析与前端结构)
3. [系统架构设计](#3-系统架构设计)
4. [技术栈规范](#4-技术栈规范)
5. [数据库设计](#5-数据库设计)
6. [API 接口设计](#6-api-接口设计)
7. [多智能体系统详细设计](#7-多智能体系统详细设计)
8. [后端目录结构](#8-后端目录结构)
9. [前端目录结构](#9-前端目录结构)
10. [开发计划与里程碑](#10-开发计划与里程碑)
11. [开发风险与注意事项](#11-开发风险与注意事项)
12. [快速启动指南（本地开发）](#12-快速启动指南本地开发)

---

## 1. 项目概述

### 1.1 项目背景与目标

本项目旨在构建一个前后端分离的在线协作学习平台，面向大学生群体，支持多名学生共同在线协作解决复杂社会议题并产出解决方案。平台核心创新点在于引入多智能体（Multi-Agent）系统，通过两层智能体架构对协作过程进行实时监测与干预，提升协作质量与学习效果。

### 1.2 核心功能

- 学生端实时聊天协作室（**五区三栏**布局：讨论区 / 写作区 / 聊天区 / 任务要求 / 任务脚本）
- 前台角色智能体（5 个角色）直接参与学生讨论，模拟良好协作组配置
- 幕后**专家委员会**（Expert Committee）实时分析协作状态，动态调度前台智能体
- 学生可通过 **@Agent 机制**主动召唤特定前台角色智能体即时作答
- 5 维度协作监测：参与度、论点多样性、协作均衡性、任务进展、情绪状态
- 混合触发机制：定时分析 + 事件驱动 + 主动召唤三轨并行
- 教师 / 研究者监控面板：实时查看协作数据与智能体干预日志（含各专家诊断报告）

### 1.3 用户角色

| **角色** | **主要操作** | **权限范围** |
|---|---|---|
| 学生（Student） | 加入房间、参与聊天、协作写作、查看讨论区、@召唤智能体 | 仅限所在房间 |
| AI 角色智能体 | 发送聊天消息、引导讨论、提供资源与反馈 | 由系统控制，不对外暴露 |
| 教师 / 管理员 | 创建任务、配置房间、查看所有协作数据与分析（含专家报告） | 全平台管理权限 |

---

## 2. UI 设计解析与前端结构

### 2.1 整体布局（五区三栏结构）

根据 UI 设计稿，学生端主界面采用**五区三栏**横向布局（左栏 35% / 中栏 35% / 右栏 30%），左栏上下分为讨论区与写作区，右栏上下分为任务要求与任务脚本，中栏为聊天区，从左到右依次为：

| **区域编号** | **区域名称** | **功能描述** | **技术要点** |
|---|---|---|---|
| ① 讨论区 | 协作编辑区（左上） | 展示讨论问题与结构化提纲，多名学生可同时编辑讨论框架 | Tiptap + Yjs CRDT 实时协同（与写作区一致） |
| ② 写作区 | 协作编辑区（左下） | 学生共同撰写最终答案/文章，支持富文本格式 | Tiptap + **Yjs CRDT 实时协同**（需配套 y-websocket 服务） |
| ③ 聊天区 | 聊天区（中间） | 实时群聊，学生与 AI 智能体共同在此发言；支持 @角色名 主动召唤 AI | WebSocket 实时通信；输入框支持 Mention 菜单 |
| ④ 任务要求 | 任务说明区（右上） | 显示任务题目与核心要求（只读） | 静态内容，由教师配置 |
| ⑤ 任务脚本 | 任务说明区（右下） | 显示分阶段活动提示与写作策略说明（只读） | 静态内容 / Markdown 渲染 |

> **关于全站统一协同策略**：讨论区与写作区均采用 Tiptap + Yjs CRDT 无锁并发协同，通过不同 Room ID 隔离：`yjs_room_discussion_{room_id}` 与 `yjs_room_writing_{room_id}`。
>
> **关于 Yjs 协同服务**：讨论区和写作区都依赖同一个 `y-websocket` 服务（Node.js），与 FastAPI 聊天 WebSocket 保持独立系统。

### 2.2 聊天区交互设计

- 每条消息显示：头像 / 角色标识、昵称 / 角色名、消息内容、时间戳
- AI 智能体消息通过角色标签（如"主持人"、"批判者"）与学生消息视觉区分
- 消息输入框支持回车发送，AI 回复以打字机效果（Streaming）呈现
- 消息列表自动滚动至底部，支持历史记录加载
- 输入框支持 @Mention：输入 `@` 弹出角色菜单（主持人/批判者/总结者/资源者/激励者）

### 2.3 Vue 组件树（推荐结构）

```
App.vue
├── router/index.js                        → 路由配置
├── views/LoginView.vue                    → 登录页
├── views/RoomView.vue                     → 主协作界面（三栏布局）
│   ├── components/layout/LeftPanel.vue    → 左栏容器
│   ├── components/editor/SharedYjsEditor.vue     → Yjs 协同富文本核心组件（复用）
│   ├── components/discussion/DiscussionArea.vue  → ①讨论区（绑定 yjs_room_discussion_{id}）
│   ├── components/writing/WritingArea.vue        → ②写作区（绑定 yjs_room_writing_{id}）
│   ├── components/chat/ChatPanel.vue      → ③聊天区容器
│   │   ├── components/chat/MessageList.vue       → 消息列表
│   │   ├── components/chat/MessageItem.vue       → 单条消息（区分学生/AI）
│   │   └── components/chat/ChatInput.vue         → 输入框（含 @Mention 菜单）
│   └── components/task/TaskPanel.vue     → 右栏任务说明
│       ├── components/task/TaskRequirements.vue  → ④任务要求
│       └── components/task/TaskScript.vue        → ⑤任务脚本
└── views/TeacherDashboard.vue             → 教师监控面板
```

---

## 3. 系统架构设计

### 3.1 整体架构概览

系统采用前后端分离架构，分为四层：

1. **前端层（Vue 3）**：学生端聊天室 + 教师监控面板
2. **后端服务层（Python FastAPI）**：REST API + WebSocket 服务端
3. **多智能体层**：幕后专家委员会（3 位分析专家 + ChiefDispatcher）+ 前台 5 个角色 Agent（调用 Anthropic API）
4. **数据层**：PostgreSQL（持久化）+ Redis（实时状态与队列）

### 3.2 多智能体架构详解

#### 3.2.1 幕后专家委员会（Expert Committee）

v1.2 将单一 Orchestrator 重构为“四角色后台委员会”：

- `CognitiveAnalyst`：认知层分析（多样性、任务进展）
- `EmotionalAnalyst`：情绪层分析（冲突/消极/焦虑）
- `InteractionAnalyst`：互动层分析（参与度、均衡性）
- `ChiefDispatcher`：综合三份专家报告并输出最终调度指令

执行方式为并发异步：先 `asyncio.gather()` 并行调用三位 Analyst，再由 `ChiefDispatcher` 汇总裁定。

**Redis 任务队列消息格式**（ChiefDispatcher 写入，AgentWorker 消费）：

```json
{
  "room_id": "uuid",
  "agent_role": "facilitator",
  "reason": "连续3分钟无人发言，需引导讨论",
  "priority": 2,
  "context_message_ids": ["uuid1", "uuid2", "..."],
  "triggered_at": "2025-01-01T12:00:00Z"
}
```

> `priority` 取值 0-3，数字越小优先级越高；`0` 预留给 C 类（@Agent 主动召唤）触发。`context_message_ids` 为本次分析所依据的消息 ID 列表，便于 AgentWorker 按需拉取上下文。

**Redis 队列实现约定（必须统一）**：

- 使用 **Sorted Set 延迟队列**，Key：`agent_queue:{room_id}`
- 写入任务：`ZADD agent_queue:{room_id} <execute_at_unix_ts> <task_json>`
- 消费任务：仅拉取 `score <= now` 的任务，消费成功后 `ZREM`
- 任务重入队（延迟 5 秒）通过更新 score 实现，不使用 `RPUSH/BLPOP`

#### 3.2.2 前台角色层（Role Agents）

5 个前台智能体各自持有角色 Prompt，监听 Redis 任务队列，被调度时生成消息并推送至聊天室：

| **角色** | **英文标识** | **核心行为描述** | **典型触发场景** |
|---|---|---|---|
| 主持人 | Facilitator | 引导讨论方向，提出结构性问题，整合发散观点 | 讨论偏题 / 陷入沉默 / 被主动 @ |
| 批判者 | Devil's Advocate | 质疑现有观点，提出反例，激发深度思考 | 观点趋同 / 论点多样性低 / 被主动 @ |
| 总结者 | Summarizer | 定期归纳讨论进展，整合不同观点的共识点 | 讨论过长 / 阶段转换时 / 被主动 @ |
| 资源者 | Resource Finder | 提供相关知识、数据或案例，补充信息基础 | 讨论缺乏依据 / 任务进展停滞 / 被主动 @ |
| 激励者 | Encourager | 识别沉默成员，主动邀请参与，调节消极情绪 | 协作均衡性低 / 情绪消极检测 / 被主动 @ |

**AgentWorker 并发控制**：当多个 Worker 进程并行运行时，需保证同一房间同一时刻只有一个 Agent 在生成发言，防止多角色同时涌入聊天室。实现方式：Worker 消费任务前先尝试获取 Redis 分布式锁：

```
SET room:{room_id}:agent_lock {worker_id} NX EX 30
```

获取锁成功才执行生成；若锁被占用则将任务重新入队（延迟 5 秒），30 秒后锁自动过期防止死锁。

**Worker 启动方式（当前版本）**：

- 当前采用**单进程内后台协程**：在 FastAPI `lifespan` 中通过 `asyncio.create_task(agent_worker.run())` 启动
- 服务关闭时通过 `task.cancel()` 优雅停止 Worker
- 当前部署模式下可用 `asyncio.Lock` 做本地并发保护；Redis 分布式锁保留用于后续多实例横向扩展

**Redis Pub/Sub 订阅机制说明**：

- **Channel 命名规范**：`room:{room_id}`，每个房间一个独立 channel
- **发布方**：FastAPI WebSocket handler 在收到并持久化学生消息后，向 `room:{room_id}` 发布消息 JSON
- **订阅方**：`ConnectionManager`（`websocket/manager.py`）在 FastAPI `lifespan` 启动时，为**每个活跃房间**启动一个独立的异步订阅协程（`asyncio.create_task`）；协程监听对应 channel，收到消息后通过本地 WebSocket 连接池广播给房间内所有已连接客户端
- **生命周期**：房间变为 `ended` 状态或服务关闭时，对应订阅协程取消；新房间激活时动态创建订阅协程

### 3.3 消息流转图

完整的一次 AI 干预流程如下：

1. 学生发送消息 → WebSocket → FastAPI → 保存至 PostgreSQL
2. Redis Pub/Sub 广播消息 → 所有在线客户端实时接收
3. 若消息包含 `mentions`（C 类触发）→ 直接写入 `priority=0` 调度任务，跳过专家分析
4. 若为 A/B 触发 → 并行调用三位 Analyst，结果汇总给 `ChiefDispatcher`
5. `ChiefDispatcher` 输出调度指令写入 Redis 队列 → 对应角色 Agent Worker 消费任务
6. Role Agent 携带角色 Prompt + 历史上下文 → **先生成 `message_id`（UUID）并创建 `status=streaming` 消息记录** → 调用 Claude API 流式生成回复
7. 生成期间逐 token 通过 WebSocket 推送（`agent:stream` 携带 `message_id`）；完成或失败时发送 `agent:stream_end`（携带 `status`），并将同一记录更新为 `status=ok/failed`
8. 教师面板实时接收协作分析数据更新

---

## 4. 技术栈规范

### 4.1 前端

| **技术/库** | **版本** | **用途** |
|---|---|---|
| Vue 3 | ^3.4 | 前端框架，Composition API |
| Vite | ^5.0 | 构建工具，开发服务器 |
| Vue Router 4 | ^4.3 | 前端路由（学生端 / 教师端） |
| Pinia | ^2.1 | 全局状态管理（用户、房间、消息） |
| reconnecting-websocket | ^4.4 | 标准 WebSocket 客户端自动重连封装 |
| Tiptap | ^2.4 | 协同富文本编辑器（讨论区与写作区） |
| Yjs | ^13.6 | CRDT 协同编辑数据结构（讨论区与写作区） |
| y-websocket | ^2.0 | Yjs WebSocket provider（同时服务讨论区与写作区） |
| Chart.js | ^4.4 | 教师端协作数据可视化 |
| TailwindCSS | ^3.4 | UI 样式框架 |
| Axios | ^1.6 | REST API HTTP 客户端 |

> **协议一致性约束**：前端聊天通信使用标准 RFC 6455 WebSocket（原生 `WebSocket` API 或 `reconnecting-websocket`），后端使用 FastAPI 原生 `WebSocket`。当前版本**不使用** Socket.IO 协议栈。

### 4.2 后端

| **技术/库** | **版本** | **用途** |
|---|---|---|
| Python | 3.11+ | 主要开发语言 |
| FastAPI | ^0.111 | Web 框架，REST API + WebSocket |
| Uvicorn | ^0.30 | ASGI 服务器 |
| SQLAlchemy 2.0 | ^2.0 | ORM，PostgreSQL 操作 |
| Alembic | ^1.13 | 数据库迁移管理 |
| asyncpg | ^0.29 | 异步 PostgreSQL 驱动 |
| redis-py (async) | ^5.0 | Redis 客户端，Pub/Sub + 任务队列 |
| anthropic | ^0.28 | Anthropic Claude API 官方 SDK |
| APScheduler | ^3.10 | 定时任务调度（专家委员会定时触发）**注意：必须使用 `AsyncIOScheduler`，禁止使用默认的 `BackgroundScheduler`，后者会阻塞 FastAPI 异步事件循环** |
| python-jose | ^3.3 | JWT 鉴权 |
| pydantic v2 | ^2.7 | 数据验证与序列化 |
| PyYAML | ^6.0 | 解析 `agent_settings.yaml` |

### 4.3 数据库

| **数据库** | **选型理由** | **存储内容** |
|---|---|---|
| PostgreSQL 16 | 关系型，结构化数据，事务支持 | 用户、房间、消息、分析快照、Agent 日志、教师报告 |
| Redis 7 | 内存型，毫秒延迟，天然支持 Pub/Sub | 在线用户列表、WebSocket 连接状态、Agent 任务队列、实时协作指标滑动窗口、Agent 发言分布式锁 |

---

## 5. 数据库设计

### 5.1 PostgreSQL 表结构

#### users --- 用户表

| **字段名** | **类型** | **说明** |
|---|---|---|
| id | UUID PK | 主键 |
| username | VARCHAR(50) | 用户名（唯一） |
| password_hash | TEXT | bcrypt 哈希 |
| role | ENUM('student','teacher') | 用户角色 |
| display_name | VARCHAR(100) | 显示名称 |
| created_at | TIMESTAMPTZ | 注册时间 |

#### rooms --- 协作房间表

| **字段名** | **类型** | **说明** |
|---|---|---|
| id | UUID PK | 主键 |
| name | VARCHAR(200) | 房间名称 |
| task_id | UUID FK | 关联任务 |
| created_by | UUID FK | 创建教师 |
| status | ENUM('waiting','active','ended') | 房间状态 |
| created_at | TIMESTAMPTZ | 创建时间 |
| ended_at | TIMESTAMPTZ | 结束时间（可空） |

#### room_members --- 房间成员关联表

| **字段名** | **类型** | **说明** |
|---|---|---|
| id | UUID PK | 主键 |
| room_id | UUID FK | 关联 rooms.id |
| user_id | UUID FK | 关联 users.id |
| joined_at | TIMESTAMPTZ | 加入时间 |

> **约束**：`UNIQUE(room_id, user_id)`，用于防止重复加入并支撑“仅房间成员可访问”权限校验。

#### tasks --- 协作任务表

| **字段名** | **类型** | **说明** |
|---|---|---|
| id | UUID PK | 主键 |
| title | TEXT | 任务标题 |
| requirements | TEXT | 任务要求（富文本 / Markdown） |
| scripts | JSONB | 分阶段任务脚本（数组结构） |
| discussion_template | TEXT | 讨论区初始模板 |
| created_by | UUID FK | 创建教师 |

> `scripts` 字段 JSON Schema（示例）：
>
> ```json
> [
>   {
>     "phase": 1,
>     "title": "问题分析阶段",
>     "duration_minutes": 10,
>     "description": "请各成员分析问题的主要成因并给出依据。",
>     "hints": ["考虑经济因素", "考虑社会文化背景"]
>   }
> ]
> ```
>
> 当前阶段判断规则：默认按 `duration_minutes` 累计时间自动推进；教师可手动覆盖当前阶段（见 6.1 PATCH 接口）。

#### messages --- 聊天消息表

| **字段名** | **类型** | **说明** |
|---|---|---|
| id | UUID PK | 主键 |
| room_id | UUID FK | 所属房间 |
| seq_num | BIGINT | 房间内单调递增顺序号（按 room_id 独立） |
| sender_type | ENUM('student','agent') | 发送者类型 |
| sender_id | UUID FK (nullable) | 学生 ID（AI 消息为 null） |
| agent_role | VARCHAR(50) (nullable) | AI 角色标识（如 facilitator） |
| content | TEXT | 消息内容 |
| status | ENUM('streaming','ok','failed') | 消息状态（AI 流式期间为 streaming） |
| created_at | TIMESTAMPTZ | 发送时间 |

> **索引**：务必创建复合索引 `CREATE INDEX idx_messages_room_seq ON messages(room_id, seq_num DESC);`，并添加唯一约束 `UNIQUE(room_id, seq_num)`。
>
> **`seq_num` 生成约定（必须遵守）**：在消息入库前，通过 Redis 原子计数器 `INCR room:{room_id}:msg_seq` 获取顺序号并写入 `seq_num`。禁止使用 `MAX(seq_num)+1` 方式，避免并发竞态导致重复或乱序。

#### analysis_snapshots --- 协作分析快照表（v1.2）

| **字段名** | **类型** | **说明** |
|---|---|---|
| id | UUID PK | 主键 |
| room_id | UUID FK | 所属房间 |
| message_seq_from | BIGINT | 本次分析起始消息顺序号（含） |
| message_seq_to | BIGINT | 本次分析结束消息顺序号（含） |
| analyzed_message_count | INT | 本次分析消息总条数 |
| participation_scores | JSONB | 各成员参与度得分 `{user_id: score}` |
| diversity_score | FLOAT | 论点多样性得分 0-1 |
| balance_score | FLOAT | 协作均衡性得分 0-1 |
| progress_score | FLOAT | 任务进展得分 0-1 |
| emotion_flags | JSONB | 情绪异常标记 `{conflict: bool, passive: bool, anxious: bool}` |
| cognitive_report | JSONB | 认知分析师诊断报告 |
| emotional_report | JSONB | 情绪分析师诊断报告 |
| interaction_report | JSONB | 互动分析师诊断报告 |
| dispatcher_summary | TEXT | ChiefDispatcher 综合分析摘要 |
| triggered_by | ENUM('timer','event') | 触发来源（`timer`=定时触发，`event`=事件驱动 A/B 类）；**C 类主动召唤不产生此表记录** |
| created_at | TIMESTAMPTZ | 分析时间 |

#### agent_interventions --- 智能体干预记录表

| **字段名** | **类型** | **说明** |
|---|---|---|
| id | UUID PK | 主键 |
| room_id | UUID FK | 所属房间 |
| snapshot_id | UUID FK (nullable) | 触发此干预的分析快照；A 类规则触发时为 `null`，B 类 AI 分析触发时填入对应 `snapshot.id`，C 类主动召唤时为 `null` |
| agent_role | VARCHAR(50) | 执行干预的角色 |
| reason | TEXT | 调度原因；B 类填入 ChiefDispatcher 给出的原因；A 类填入触发规则描述（如 `"连续5条消息来自同一人"`）；**C 类填入学生的原始 @ 消息内容** |
| message_id | UUID FK | 干预产生的消息 ID |
| created_at | TIMESTAMPTZ | 干预时间 |

---

## 6. API 接口设计

### 6.1 REST API 端点（FastAPI）

#### 认证模块

| **方法** | **路径** | **描述** | **认证要求** |
|---|---|---|---|
| POST | /api/auth/register | 用户注册 | 无 |
| POST | /api/auth/login | 登录，返回 JWT Token | 无 |
| GET | /api/auth/me | 获取当前用户信息 | JWT |

#### 房间模块

| **方法** | **路径** | **描述** | **认证要求** |
|---|---|---|---|
| GET | /api/rooms?status=active | 获取房间列表（支持 status 过滤） | JWT |
| POST | /api/rooms | 创建房间（教师） | JWT + 教师角色 |
| GET | /api/rooms/{room_id} | 获取房间详情 | JWT |
| POST | /api/rooms/{room_id}/join | 加入房间（写入 room_members） | JWT |
| PATCH | /api/rooms/{room_id} | 更新房间状态（active/ended） | JWT + 教师角色 |
| GET | /api/rooms/{room_id}/messages | 获取历史消息（游标分页） | JWT + 房间成员 |

> **历史消息分页规范（游标分页）**：使用基于 `seq_num` 的游标分页，而非页码分页（避免实时消息插入导致翻页重复）。
> - 请求参数：`?before_seq={seq_num}&limit=50`（`before_seq` 不传时返回最新 50 条）
> - 返回结构：`{ "messages": [...], "has_more": bool, "oldest_seq": bigint }`
> - 前端下拉加载更多时，将当前列表中最小的 `seq_num` 作为 `before_seq` 传入下一次请求
> - 返回消息按 `seq_num` **升序**排列，便于前端直接追加渲染

#### 任务模块

| **方法** | **路径** | **描述** | **认证要求** |
|---|---|---|---|
| GET | /api/tasks | 获取任务列表 | JWT |
| POST | /api/tasks | 创建任务 | JWT + 教师角色 |
| GET | /api/tasks/{task_id} | 获取任务详情 | JWT |
| PATCH | /api/tasks/{task_id} | 更新任务内容/脚本 | JWT + 教师角色 |

#### 教师监控模块

| **方法** | **路径** | **描述** | **认证要求** |
|---|---|---|---|
| GET | /api/analytics/rooms/{room_id}/snapshots | 获取协作分析快照列表 | JWT + 教师 |
| GET | /api/analytics/rooms/{room_id}/interventions | 获取干预记录 | JWT + 教师 |
| GET | /api/analytics/rooms/{room_id}/summary | 获取整体协作摘要 | JWT + 教师 |

### 6.2 WebSocket 事件协议

**WebSocket 端点**：`wss://{host}/ws/{room_id}`

> **鉴权说明**：**禁止**将 JWT 作为 URL 查询参数传递（如 `?token=...`），因为 JWT 会被记录在服务器访问日志、浏览器历史和 HTTP Referer 头中，存在安全风险。正确做法：客户端建立 WebSocket 连接后，立即发送第一条 `auth` 帧进行鉴权：
>
> ```json
> { "type": "auth", "token": "<jwt>" }
> ```
>
> 服务端收到 `auth` 帧后验证 JWT，验证失败则主动关闭连接（code 4001）。在鉴权完成前，服务端不处理任何其他帧。
>
> **鉴权超时约束**：客户端需在连接建立后 **10 秒内**发送 `auth` 帧；超时则服务端关闭连接（code 4002, reason=`Auth timeout`），避免未鉴权连接长期占用资源。
>
> 生产环境必须使用 `wss://`（TLS），不得使用明文 `ws://`。

| **事件名** | **方向** | **数据结构** | **说明** |
|---|---|---|---|
| auth | 客→服 | `{type: "auth", token: string}` | 连接建立后第一帧，完成鉴权 |
| chat:message | 客→服 | `{content: string, mentions?: string[]}` | 学生发送聊天消息（`mentions` 用于 @Agent 主动召唤） |
| chat:new_message | 服→客 | `{id, sender_type, sender_id, agent_role, content, created_at}` | 广播新消息（学生或 AI） |
| room:user_join | 服→客 | `{user_id, display_name}` | 用户加入房间广播 |
| room:user_leave | 服→客 | `{user_id}` | 用户离开房间广播 |
| agent:typing | 服→客 | `{agent_role, is_typing: bool}` | AI 打字状态（打字机效果） |
| agent:stream | 服→客 | `{agent_role, token, message_id}` | AI 流式输出逐 token 推送 |
| agent:stream_end | 服→客 | `{agent_role, message_id, status: "ok"\|"failed"}` | AI 流式输出结束，前端据此将临时流切换为持久化消息 |
| analysis:update | 服→客 | `{snapshot}` | 向教师端推送最新分析快照 |

> `chat:new_message` 前端渲染约定：根据 `sender_type` 区分样式；`student` 显示用户头像/昵称，`agent` 显示角色图标与 `agent_role` 标签（颜色映射在前端常量中维护）。
>
> `agent:stream.message_id` 为流式开始前预分配的消息 ID；前端应以 `message_id` 聚合 token，收到对应 `chat:new_message` 或 `agent:stream_end` 后将临时流式内容切换为持久化消息。
>
> `analysis:update` 只发送给教师连接，不广播给学生连接。

---

## 7. 多智能体系统详细设计

### 7.1 专家委员会 Prompt 框架

v1.2 将 Orchestrator Prompt 拆分为四类：

- `CognitiveAnalyst` Prompt：输出 `diversity_score`、`progress_score` 与认知依据
- `EmotionalAnalyst` Prompt：输出 `emotion_flags` 与情绪依据
- `InteractionAnalyst` Prompt：输出 `participation_scores`、`balance_score`
- `ChiefDispatcher` Prompt：输入三份专家 JSON 报告 + 当前协作阶段信息，输出 `interventions` 与 `dispatcher_summary`

> **ChiefDispatcher 输入说明（重要）**：ChiefDispatcher **不直接接收原始聊天记录**。其输入由两部分组成：① 当前协作阶段信息（阶段编号、阶段目标、已用时长）；② 三位分析专家各自输出的 JSON 结构化报告（`cognitive_report`、`emotional_report`、`interaction_report`）。原始聊天记录由三位 Analyst 各自独立分析，ChiefDispatcher 只负责综合裁定与调度，实现职责分离。

三位 Analyst（CognitiveAnalyst / EmotionalAnalyst / InteractionAnalyst）并发分析时遵循下述输入上下文约束：

**Analyst 输入上下文：**

- 任务说明（task.requirements + task.scripts）
- 聊天记录（消息 + 发送者 + 时间戳），按 **Token Budget** 动态截断（整条消息粒度）
- 参与者列表与基础统计（各人发言次数、字数）
- 当前协作阶段（由教师配置或系统推断）

**Token Budget 策略（固定约定）**：

- 上下文总预算按模型窗口配置（默认 128k），其中预留 `8000 tokens` 给聊天历史
- 仅按“整条消息”截断，不截断单条消息内容
- Token 计算优先使用 Anthropic SDK 计数能力（如 `count_tokens`）；无计数接口时使用估算并保守留余量
- System Prompt 与任务脚本的 token 开销在服务启动时预估并缓存，避免每次重复计算
- 若发生截断，在 Prompt 中追加说明：`以下为按 token budget 截断后的近期消息`

**ChiefDispatcher 输出 JSON 格式（强制 JSON 模式）：**

```json
{
  "dispatcher_summary": "100字以内综合分析",
  "interventions": [
    {"role": "encourager", "reason": "user_id_2长时间未发言", "priority": 1}
  ]
}
```

> **注意**：ChiefDispatcher 的输出**仅包含 `dispatcher_summary` 和 `interventions` 两个字段**，不重复输出各 Analyst 已产出的分数字段。

**数据库写入职责划分（committee.py 实现时必须遵守）：**

| **写入字段** | **数据来源** | **写入时机** |
|---|---|---|
| `diversity_score`、`progress_score`、`cognitive_report` | CognitiveAnalyst 输出 | asyncio.gather 完成后，committee.py 直接解析写入 |
| `emotion_flags`、`emotional_report` | EmotionalAnalyst 输出 | asyncio.gather 完成后，committee.py 直接解析写入 |
| `participation_scores`、`balance_score`、`interaction_report` | InteractionAnalyst 输出 | asyncio.gather 完成后，committee.py 直接解析写入 |
| `dispatcher_summary`、`interventions`（→ agent_interventions 表） | ChiefDispatcher 输出 | ChiefDispatcher 调用完成后，committee.py 解析写入 |

即：`committee.py` 在 `asyncio.gather` 拿到三份 Analyst 结果后，**先将分数字段 upsert 进 `analysis_snapshots`，再将三份报告作为输入构建 ChiefDispatcher 的请求，最后将 `dispatcher_summary` 更新至同一条快照记录，并将 `interventions` 列表写入 `agent_interventions` 表**。整个流程在同一个 `snapshot_id` 下完成。

### 7.2 各角色 Agent Prompt 框架

每个角色 Agent 的 System Prompt 结构：

1. 角色定义（你是谁、你的核心职责）
2. 协作背景（当前任务描述、小组成员信息）
3. 行为准则（何时说话、说话风格、禁止事项）
4. 干预指令（ChiefDispatcher 发来的本次具体任务：原因、目标、建议策略）
5. 历史消息上下文（最近 20-30 条消息）

**被主动召唤时的动态 Prompt 追加（C 类触发专属）：**

当 Agent 是通过 C 类触发（学生 @Agent）被调度时，构建 Prompt 的逻辑需在标准 System Prompt 末尾动态追加一段上下文说明，明确告知角色当前处境，示例如下：

```
【系统提示】：用户 {display_name} 刚刚在聊天中直接 @ 了你。请针对他/她的这条提问给出直接、正面的回应。不要长篇大论，保持你作为 {role_name} 的角色设定。
```

> 此追加指令由 `role_agents.py` 中的 Prompt 构建函数在检测到任务来源为 `C 类（mention）` 时注入，B 类（分析驱动）与 A 类（规则触发）场景下不追加此段，保持标准格式。

**关键约束（所有角色通用）：**

- 回复长度控制在 80-150 字，符合聊天语境
- 语气自然，像真实的组员，而非 AI 助手
- 不得暴露自己是 AI 或被系统调度（除非特别设计）
- 不得同时多角色连续发言超过 2 次（由 ChiefDispatcher 控制调度频率）

### 7.3 触发机制详细说明

触发检测器分为三类，需明确区分实现方式：

#### A 类：轻量规则检测器（分为同步与时间轮询两类）

1) **同步规则**：在消息处理管道中，每条新消息入库后实时判断。
2) **时间轮询规则**：由 `scheduler.py` 每 30 秒轮询一次活跃房间状态。

满足条件后直接向 Redis 队列写入调度指令，**不需要**先调用专家委员会：

| **检测事件** | **触发条件** | **优先调度角色** |
|---|---|---|
| 单人垄断检测 | 滑动窗口内连续 5 条消息来自同一人 | Encourager |
| 阶段超时检测 | 某阶段时间超出教师预设限制 | Facilitator |

**A 类时间轮询规则（scheduler）**：

| **检测事件** | **触发条件** | **优先调度角色** |
|---|---|---|
| 沉默检测 | 距最近一条消息超过 `SILENCE_THRESHOLD_SECONDS`（默认 180 秒） | Facilitator 或 Encourager |

#### B 类：AI 分析结果驱动（异步，专家委员会返回后二次决策）

以下场景**无法通过简单规则判断**，需借助专家委员会分析结果驱动。委员会完成分析、写入 `analysis_snapshots` 后，系统检查输出 JSON 中的相应字段，若满足条件则**立即追加**一次调度：

| **检测事件** | **判断依据（来自专家委员会输出 JSON）** | **优先调度角色** |
|---|---|---|
| 观点趋同检测 | `diversity_score < 0.3` | Devil's Advocate |
| 情绪冲突检测 | `emotion_flags.conflict == true` | Summarizer 或 Encourager |
| 消极情绪检测 | `emotion_flags.passive == true` 且 `balance_score < 0.4` | Encourager |

#### C 类：主动召唤触发（同步，用户 @Agent）

- 学生消息包含 `mentions` 字段时立即触发
- 直接写入 `priority=0` 的队列任务，跳过专家委员会分析
- `max_mentions_per_message` 由 `agent_settings.yaml` 控制（默认 1）
- 典型消息：`@资源者 帮我找这项议题的最新数据`
- **C 类触发不产生 `analysis_snapshots` 记录**；仅向 `agent_interventions` 表写入一条干预记录（`snapshot_id` 为 `null`，`reason` 填入学生原始 @ 消息内容）

> **多人同时 @ 的并发排队保障**：若多名学生在短时间内分别 @ 不同的 AI 角色，每条召唤请求均以 `priority=0` 独立写入 `agent_queue:{room_id}` Sorted Set。AgentWorker 在消费每个任务前必须先竞争获取 Redis 分布式锁 `room:{room_id}:agent_lock`（参见 3.2.2 节）。获锁成功的 Worker 独占生成权，其余被召唤的任务在队列中等待（约 5 秒后重试抢锁），确保**同一聊天室同一时刻只有一个 AI 在流式输出**，防止多角色同时涌入造成信息爆炸。

#### 定时触发

- 默认每 5 分钟触发一次专家委员会分析
- 可由教师在创建房间时配置分析间隔（3 / 5 / 10 分钟）
- 房间开始后前 2 分钟不触发（等待学生热场）

#### 防重复触发

- 同一 A 类规则在同一房间内，1 分钟内不重复触发，通过 Redis Key `trigger_lock:{room_id}:{trigger_type}` 设置 TTL 实现
- B 类分析结果驱动的调度，在同一快照处理完毕后不重复追加

---

## 8. 后端目录结构

推荐 FastAPI 项目结构：

```
backend/
├── app/
│   ├── main.py                  → FastAPI 入口，注册路由和中间件
│   ├── config.py                → 环境变量与配置加载
│   ├── config/
│   │   └── agent_settings.yaml  → AI 非机密参数集中配置（阈值/节奏/模型）
│   ├── dependencies.py          → 通用依赖（认证、DB 会话）
│   ├── routers/                 → 路由模块
│   │   ├── auth.py
│   │   ├── rooms.py
│   │   ├── tasks.py
│   │   └── analytics.py
│   ├── models/                  → SQLAlchemy ORM 模型
│   │   ├── user.py
│   │   ├── room.py
│   │   ├── room_member.py
│   │   ├── message.py
│   │   ├── task.py
│   │   └── analysis.py
│   ├── schemas/                 → Pydantic 请求/响应 Schema
│   ├── services/                → 业务逻辑层
│   │   ├── auth_service.py
│   │   ├── room_service.py
│   │   └── message_service.py
│   ├── agents/                  → 多智能体模块
│   │   ├── committee.py         → 专家委员会编排入口：orchestrate 三位 Analyst 并发调用，将结果传入 ChiefDispatcher，统一写入数据库
│   │   ├── role_agents.py       → 5 个前台角色 Agent 基类与实现
│   │   ├── agent_worker.py      → Redis 任务队列消费 Worker（含分布式锁逻辑）
│   │   ├── queue.py             → Sorted Set 延迟队列封装（ZADD/ZRANGEBYSCORE/ZREM）
│   │   └── prompts/             → 所有 Agent Prompt 模板文件（.txt / .jinja2）
│   ├── background_experts/      → 幕后专家委员会四成员实现
│   │   ├── cognitive_analyst.py   → CognitiveAnalyst：输出 diversity_score、progress_score、cognitive_report
│   │   ├── emotional_analyst.py   → EmotionalAnalyst：输出 emotion_flags、emotional_report
│   │   ├── interaction_analyst.py → InteractionAnalyst：输出 participation_scores、balance_score、interaction_report
│   │   └── chief_dispatcher.py    → ChiefDispatcher：接收三份专家报告，输出 dispatcher_summary 与 interventions
│   ├── analysis/                → 协作分析引擎
│   │   ├── metrics.py           → 5 维度计算逻辑
│   │   ├── triggers.py          → 事件触发检测逻辑（A类规则 + B类结果解析）
│   │   └── scheduler.py        → 定时任务配置（APScheduler AsyncIOScheduler）
│   ├── websocket/               → WebSocket 连接管理
│   │   ├── manager.py           → 房间连接管理器
│   │   └── handlers.py          → 消息事件处理器（含首帧鉴权逻辑）
│   └── db/                      → 数据库连接
│       ├── session.py           → SQLAlchemy 异步会话
│       └── redis_client.py      → Redis 异步客户端
├── alembic/                     → 数据库迁移
├── tests/                       → 单元与集成测试
├── .env                         → 环境变量（不提交 Git）
├── requirements.txt             → 依赖清单
└── docker-compose.yml           → 本地开发环境
```

> `main.py` 使用 `lifespan` 启动/停止 `AgentWorker` 后台任务；`handlers.py` 中首帧鉴权需加 10 秒超时保护。
>
> `ConnectionManager` 需在连接建立后记录用户角色（`student`/`teacher`），并提供 `broadcast_to_teachers(room_id, data)`；`analysis:update` 必须仅推送给教师连接。

---

## 9. 前端目录结构

推荐 Vue 3 项目结构：

```
frontend/
├── src/
│   ├── main.js                  → 应用入口
│   ├── App.vue                  → 根组件
│   ├── router/                  → Vue Router 路由配置
│   ├── stores/                  → Pinia 状态管理
│   │   ├── auth.js              → 用户认证状态
│   │   ├── room.js              → 房间与成员状态
│   │   ├── chat.js              → 消息列表状态
│   │   └── agent.js             → AI 智能体状态（打字、流式）
│   ├── views/                   → 页面视图
│   │   ├── LoginView.vue        → 登录页
│   │   ├── LobbyView.vue        → 大厅（选择/加入房间）
│   │   ├── RoomView.vue         → 主协作页面（三栏布局）
│   │   └── TeacherDashboard.vue → 教师监控面板
│   ├── components/              → 可复用组件
│   │   ├── layout/              → LeftPanel, RightPanel, MainLayout
│   │   ├── chat/                → MessageList, MessageItem, ChatInput（含 Mention）, AgentTypingIndicator
│   │   ├── editor/              → SharedYjsEditor, DiscussionEditor, WritingEditor
│   │   ├── task/                → TaskRequirements, TaskScript
│   │   ├── dashboard/           → AnalyticsChart, InterventionLog, ParticipationHeatmap
│   │   └── common/              → Button, Avatar, Badge, Modal 等基础组件
│   ├── composables/             → Vue Composable 逻辑复用
│   │   ├── useWebSocket.js      → WebSocket 连接管理（含首帧鉴权发送逻辑）
│   │   ├── useChat.js           → 聊天逻辑（含 mentions 字段）
│   │   ├── useAgentStream.js    → 流式输出处理
│   │   └── useMention.js        → @Mention 菜单逻辑
│   ├── services/                → API 调用封装
│   │   ├── api.js               → Axios 实例与拦截器
│   │   ├── authApi.js
│   │   ├── roomApi.js
│   │   └── analyticsApi.js
│   └── utils/                   → 工具函数
├── index.html                   → 入口 HTML
├── vite.config.js               → Vite 配置
└── tailwind.config.js           → Tailwind 配置
```

---

## 10. 开发计划与里程碑

本项目共分为 8 个开发阶段，每个阶段结束后均可独立演示，循序渐进构建完整系统。

| **阶段** | **名称** | **预计周期** | **核心里程碑** |
|---|---|---|---|
| P1 | 基础框架搭建 | 1-2 周 | 项目跑通，可登录，看到三栏界面骨架 |
| P2 | 实时聊天室 | 1-2 周 | 多人实时文字聊天，消息持久化 |
| P3 | 单个 AI 角色接入 | 1 周 | Facilitator 角色会在聊天室发言 |
| P4 | 完整多智能体体系 | 2 周 | 5 个角色 Agent + 基础专家委员会运作 |
| P5 | 幕后专家委员会（分析引擎）开发 | 1-2 周 | 专家委员会并发分析 + 精准干预 + @Agent 召唤 |
| P6 | UI 精修与体验优化 | 1-2 周 | 五区三栏视觉完善、编辑体验优化、交互细节打磨 |
| P7 | 教师监控面板 | 1 周 | 数据可视化 Dashboard 上线 |
| P8 | 集成测试与打磨 | 1 周 | 完整场景 E2E 测试，性能优化 |

---

### 阶段一：基础框架搭建

**⏱ 1-2 周**

**阶段目标：** 搭建前后端基础项目，实现用户认证、房间管理与基础界面，确保核心技术路线跑通。

**开发任务：**

1. 初始化 Vue 3 + Vite 前端项目，配置 TailwindCSS、Vue Router、Pinia
2. 初始化 FastAPI 后端项目，配置目录结构、环境变量、Uvicorn
3. 搭建 Docker Compose（**纯数据库模式**：仅 PostgreSQL + Redis，便于开发热重载；全栈容器模式留至集成测试阶段使用）
4. 设计并执行数据库 Alembic 初始迁移：users、rooms、room_members、tasks 表
5. 实现用户注册/登录 API + JWT 鉴权中间件
6. 前端实现登录页 + 注册页，接入 Auth API
7. 实现房间列表 API + 创建房间 API（教师）
8. 前端实现大厅页面（房间列表 + 加入按钮）
9. 前端实现主协作页面功能骨架（三栏布局 + 可联调占位数据，供 P2-P5 持续验证）
10. 部署到本地，验证前后端联通

**演示交付物：** P1 演示版本 --- 基础架构 Demo

*演示者可以：打开浏览器 → 注册账号 → 登录 → 看到房间列表 → 进入房间看到三栏界面（聊天区空白但布局正确）。可同时打开多个浏览器标签验证多用户支持。*

---

### 阶段二：实时聊天室

**⏱ 1-2 周**

**阶段目标：** 实现完整的 WebSocket 实时聊天功能，多名学生可以在同一房间实时收发消息，消息持久化至数据库。

**开发任务：**

1. FastAPI 实现 WebSocket 端点 `/ws/{room_id}`，实现首帧 `auth` 鉴权逻辑
2. 实现 ConnectionManager：管理房间内所有 WebSocket 连接，支持广播
3. Redis Pub/Sub：跨实例广播（为后续多进程部署做准备）
4. 实现消息存储 Service：收到消息写入 PostgreSQL messages 表
5. 实现历史消息 API：`GET /api/rooms/{room_id}/messages`（分页）
6. 前端 `useWebSocket` composable：连接管理、断线重连，连接成功后立即发送首帧 `auth` 鉴权
7. 前端 ChatPanel 组件：MessageList + ChatInput，实时渲染新消息
8. MessageItem 组件：显示头像、昵称、内容、时间戳
9. 进入房间自动加载历史消息（最近 50 条）
10. 在线用户列表（Redis 维护，WebSocket 事件同步）

**演示交付物：** P2 演示版本 --- 多人实时聊天 Demo

*演示者用 3 个不同账号分别进入同一房间，互相发送消息，所有客户端实时显示消息。刷新页面后历史消息保留。*

---

### 阶段三：单个 AI 角色接入

**⏱ 1 周**

**阶段目标：** 接入 Anthropic Claude API，实现第一个 AI 角色智能体（主持人 Facilitator）能够主动在聊天室中发言，验证整条 AI 消息生成 → 推送 → 落库链路。

**开发任务：**

1. 配置 Anthropic API Key，封装 Claude API 调用工具函数
2. 编写 Facilitator 角色的 System Prompt（角色定义 + 行为准则）
3. 实现简单触发逻辑：检测到房间沉默 3 分钟后触发 Facilitator（A 类规则检测器）
4. 实现 AI 消息生成流程：构建 Prompt → 调用 Claude API 流式生成
5. 实现流式输出（Streaming）：流式开始前预分配 `message_id` 并写入 `status=streaming`；逐 token 通过 WebSocket 推送；结束后更新为 `status=ok`，中断时更新 `status=failed`
6. 前端 `useAgentStream` composable：接收 `agent:stream` 事件，逐字渲染
7. AgentTypingIndicator 组件：显示 AI 正在打字动画
8. MessageItem 区分 AI 消息样式（角色标签颜色、头像）
9. AI 消息存入 PostgreSQL（`sender_type = agent`）
10. 手动触发接口（调试用）：`POST /api/debug/trigger-agent`

**演示交付物：** P3 演示版本 --- AI 角色首次发言 Demo

*演示者进入房间聊几句话，然后停止发言。约 3 分钟后（可配置为 30 秒用于演示），聊天区出现主持人图标和打字动画，随后主持人的引导性发言以流式打字效果逐字出现。*

---

### 阶段四：完整多智能体体系

**⏱ 2 周**

**阶段目标：** 完成全部 5 个前台角色 Agent 的 Prompt 设计与实现，以及基础版专家委员会的分析与调度能力。

**开发任务：**

1. 设计并编写 5 个角色的 System Prompt（主持人、批判者、总结者、资源者、激励者）
2. 实现通用 RoleAgent 基类：接受调度指令，构建完整 Prompt，调用 Claude API
3. 实现 Redis 任务队列：基于 Sorted Set 的延迟队列（支持延迟重入队），ChiefDispatcher 写入，AgentWorker 按 `score<=now` 消费
4. 实现 AgentWorker：由 FastAPI `lifespan` 启动后台协程监听队列，获取锁后调度对应角色 Agent
5. 实现基础版专家委员会：三位分析专家并发输出 + ChiefDispatcher 汇总调度
6. 实现 A 类事件触发检测器（同步规则：垄断、超时；时间轮询规则：沉默）
7. 控制调度频率：同一角色短时间内不重复发言，总 AI 占比不超过设定比例
8. 前端 AgentPanel（可选）：显示当前活跃的 AI 角色列表
9. 测试各角色在不同场景下的发言质量与合理性
10. 调优：根据测试反馈调整各角色 Prompt

**演示交付物：** P4 演示版本 --- 多角色协同 Demo

*演示者准备脚本化场景：① 学生们都表示同意某观点 → 批判者自动出现提出反对意见；② 某学生一直沉默 → 激励者主动点名邀请；③ 讨论持续一段时间 → 总结者归纳进展。展示 5 种角色各至少出现一次。*

---

### 阶段五：幕后专家委员会（分析引擎）开发

**⏱ 1-2 周**

**阶段目标：** 实现基于专家委员会的 5 维度协作分析，完成 B 类分析驱动与 C 类 @Agent 主动召唤，干预决策更智能，分析结果完整持久化。

**开发任务：**

1. 实现 `metrics.py`：基于聊天记录计算参与度、均衡性等可量化指标
2. 完成三位分析专家 Prompt（认知/情绪/互动）与 ChiefDispatcher Prompt（字段名与数据库保持一致）
3. 实现 `committee.py`：`asyncio.gather` 并发调用三位专家并汇总给 ChiefDispatcher
4. 分析结果写入 `analysis_snapshots` 表（含 `cognitive_report`、`emotional_report`、`interaction_report`、`dispatcher_summary`），干预记录写入 `agent_interventions` 表
5. 实现 APScheduler `AsyncIOScheduler` 定时任务：每 5 分钟触发专家委员会
6. 实现 B 类分析结果驱动调度 + C 类 @Agent 主动召唤（`mentions` 直达 `priority=0`）
7. 实现 `GET /api/analytics/rooms/{room_id}/snapshots` API
8. 实现 `GET /api/analytics/rooms/{room_id}/interventions` API
9. WebSocket 向教师端推送实时分析更新（`analysis:update` 事件）
10. 增加防重复触发机制：同一触发条件 1 分钟内不重复激活（Redis Key TTL）

**演示交付物：** P5 演示版本 --- 智能分析干预 Demo

*演示者展示：① 触发一次定时分析，后台三位 Analyst 并发调用（可通过日志观察 asyncio.gather 并行完成），ChiefDispatcher 汇总后输出调度指令；② 教师端实时出现包含 cognitive_report / emotional_report / interaction_report 三份专家诊断的分析快照；③ 学生输入 `@资源者 ...`，触发 C 类 priority=0 高优先级即时响应，Agent 无需等待专家分析直接发言。*

---

### 阶段六：UI 精修与体验优化

**⏱ 1-2 周**

**阶段目标：** 在已有功能骨架基础上按 UI 设计稿完成视觉与交互精修，完善讨论区/写作区编辑体验与聊天区展示细节。

**开发任务：**

1. 按设计稿还原五区三栏布局（左栏 35% / 中栏 35% / 右栏 30%），适配响应式
2. 讨论区接入 Tiptap + Yjs（无锁多人协同）
3. 接入 Tiptap + Yjs 实现写作区（② Writing Area）实时协同编辑；**`y-websocket` 同时承载讨论区与写作区**，前端通过不同 Room ID 隔离
4. 实现任务说明区（④⑤）：Markdown 渲染任务要求与分阶段脚本
5. 完善聊天区 UI：消息气泡、AI 角色颜色标签、时间分隔线
6. 实现工具栏（粗体/斜体/列表等富文本格式按钮）
7. 完善大厅页面：房间卡片展示，状态徽标（等待中/进行中）
8. 实现全局通知（Toast）：用户加入/离开、AI 开始发言提示
9. 深色/浅色主题切换（可选）

**演示交付物：** P6 演示版本 --- 高保真界面 Demo

*演示者展示完整的三栏协作界面：左栏讨论区与写作区均为 Yjs 多光标实时协同，中间聊天区正常运作，输入框支持 @Mention，右栏任务说明清晰展示。整体视觉与 UI 设计稿高度一致。*

---

### 阶段七：教师监控面板

**⏱ 1 周**

**阶段目标：** 基于已有分析数据，实现教师端可视化监控面板，展示协作实时状态、历史分析趋势与 AI 干预日志。

**开发任务：**

1. 教师端路由与鉴权（仅 teacher 角色可访问）
2. 实现房间选择器：教师可切换查看不同房间
3. 实时参与度看板：各成员发言次数环形图（Chart.js）
4. 5 维度雷达图：当前协作状态评分可视化
5. 时间轴折线图：各维度得分随时间变化趋势
6. 干预记录列表：时间、触发角色、触发原因、干预效果
7. WebSocket 接入：教师面板实时接收 `analysis:update` 事件并刷新图表
8. 协作摘要导出（PDF / JSON 格式）（可选）
9. 消息监控流：教师可实时查看房间聊天内容（只读）

**演示交付物：** P7 演示版本 --- 教师面板 Demo

*演示者打开教师账号，选择一个活跃房间，看到实时更新的参与度图表、5 维度雷达图，以及 AI 干预记录日志。学生端每次 AI 发言后，教师端自动更新分析数据。*

---

### 阶段八：集成测试与打磨

**⏱ 1 周**

**阶段目标：** 完整端到端测试，修复 Bug，优化性能瓶颈，完善代码注释与用户操作文档。

**开发任务：**

1. 编写完整的 E2E 测试场景（5 名学生 + 教师 + AI 协作完整流程）
2. 性能压测：WebSocket 并发连接数，Claude API 调用延迟控制
3. Claude API 调用限流保护（防止 429 Too Many Requests）
4. 错误处理完善：断线重连、API 失败降级、消息发送失败提示
5. 安全加固：XSS 防护、CSRF、Rate Limiting、敏感信息脱敏
6. 移动端适配（可选，三栏布局在小屏幕折叠）
7. 编写用户操作手册（学生端 + 教师端）
8. 编写开发者 README：本地启动、环境变量说明、部署指南
9. 配置生产环境 Docker Compose / CI CD 流水线（可选）

**演示交付物：** P8 最终演示版本 --- 完整系统 Demo

*完整演示一场 20 分钟的协作学习活动：5 名学生讨论社会议题，AI 多角色介入，教师实时监控。整个流程流畅无报错，AI 干预合理且自然，教师面板数据准确反映协作质量。*

---

## 11. 开发风险与注意事项

### 11.1 技术风险

| **风险项** | **风险等级** | **应对措施** |
|---|---|---|
| Claude API 延迟导致 AI 响应慢 | 中 | 流式输出（Streaming）缓解感知延迟；AI 消息异步发送，不阻塞聊天室 |
| Yjs 协同编辑冲突处理复杂 | 中 | Yjs 自带 CRDT 算法处理冲突；初期可简化为单用户写作区降低复杂度 |
| 专家委员会 JSON 输出不稳定 | 中 | 对四类 Agent 使用结构化输出约束；增加输出校验与回退逻辑 |
| Claude API Rate Limit（429） | 高 | 维护调用队列，限制并发调用数；加指数退避重试；监控 Token 用量 |
| WebSocket 多实例广播问题 | 低 | 使用 Redis Pub/Sub 跨实例广播（已在架构中设计） |
| AI 角色暴露自己是 AI | 低 | Prompt 中明确禁止；增加输出过滤层检查敏感词 |

### 11.2 开发建议

- 阶段一务必先跑通 Docker Compose 全栈环境，避免后续环境问题拖慢进度
- 阶段三完成后即进行 Prompt 效果评估，不满意的 Prompt 越早调整越好
- 协同编辑（Yjs y-websocket）与聊天 WebSocket 建议分开两个端点，避免互相影响
- Claude API Key 不要硬编码，统一通过 `.env` 文件管理，不要提交至 Git
- 每个阶段结束后务必录制 Demo 视频，方便后续向利益相关方展示进展
- 建议使用 GitHub Projects 或 Notion 追踪各任务状态，便于协作开发

### 11.3 环境变量清单（`.env` 仅保留机密信息）

> v1.2 变更：`ANALYSIS_INTERVAL_MINUTES` 与 `SILENCE_THRESHOLD_SECONDS` 已迁移至 `agent_settings.yaml`。

| **变量名** | **示例值** | **说明** |
|---|---|---|
| DATABASE_URL | `postgresql+asyncpg://...` | PostgreSQL 连接字符串 |
| REDIS_URL | `redis://localhost:6379/0` | Redis 连接地址 |
| ANTHROPIC_API_KEY | `sk-ant-...` | Anthropic Claude API 密钥 |
| JWT_SECRET_KEY | （随机 64 字符） | JWT 签名密钥 |
| CORS_ORIGINS | `http://localhost:5173` | 允许的前端来源 |
| YJS_WEBSOCKET_PORT | `1234` | y-websocket 服务端口（与 FastAPI 分开） |

### 11.4 集中化 AI 微调配置文件（`agent_settings.yaml`）

`backend/app/config/agent_settings.yaml` 统一管理非机密 AI 参数（触发阈值、调度节奏、模型版本、@Agent 规则），避免硬编码散落在业务代码中。

建议最少包含以下配置分组：

- `timing`：`silence_threshold_seconds`、`analysis_interval_minutes`、`warmup_minutes`、`agent_cooldown_seconds`
- `thresholds`：`diversity_score_threshold`、`balance_score_threshold`、`monopoly_message_count`
- `models`：三位分析专家与 `chief_dispatcher` 的模型版本和 token budget
- `mention`：`enabled`、`priority`、`max_mentions_per_message`

**配置文件结构示例（最小完整版）**：

```yaml
# backend/app/config/agent_settings.yaml

timing:
  silence_threshold_seconds: 180       # 沉默检测阈值（秒）
  analysis_interval_minutes: 5         # 专家委员会定时分析间隔（分钟）
  warmup_minutes: 2                    # 房间开始后的热场等待时间
  agent_cooldown_seconds: 60           # 同一角色连续发言最短间隔（秒）
  global_intervention_limit_per_hour: 12  # 房间每小时最大干预次数

thresholds:
  diversity_score_threshold: 0.3       # 低于此值触发 B 类观点趋同检测
  balance_score_threshold: 0.4         # 低于此值触发 B 类消极情绪检测
  monopoly_message_count: 5            # A 类单人垄断检测连续消息数

models:
  cognitive_analyst:
    model_version: "claude-3-5-haiku-20241022"
    history_token_budget: 8000
  emotional_analyst:
    model_version: "claude-3-5-haiku-20241022"
    history_token_budget: 8000
  interaction_analyst:
    model_version: "claude-3-5-haiku-20241022"
    history_token_budget: 8000
  chief_dispatcher:
    model_version: "claude-3-5-sonnet-20241022"
    history_token_budget: 4000
  role_agents:
    model_version: "claude-3-5-sonnet-20241022"
    history_token_budget: 6000

mention:
  enabled: true
  priority: 0                          # C 类触发优先级（0 为最高）
  max_mentions_per_message: 1          # 每条消息最多 @ 几个角色
```

**加载方式**：后端使用 **PyYAML** 读取 YAML 文件，并通过 **Pydantic BaseSettings / BaseModel** 对配置内容进行强类型校验（字段类型、取值范围），在应用启动（`lifespan`）阶段实例化为全局单例配置对象。`triggers.py`、`scheduler.py`、`committee.py`、`agent_worker.py` 通过依赖注入读取该对象，确保参数改动无需修改业务代码。

**关于配置生效方式**：当前版本配置在**应用启动时一次性加载**，修改 `agent_settings.yaml` 后需**重启后端服务**方可生效（`uvicorn --reload` 模式下文件变更会自动触发重启）。若后续需要支持热更新（无需重启即时生效），可在 `config.py` 中引入定时轮询（如每分钟检查文件 `mtime` 并重载）或使用 `watchfiles` 库监听文件变更，届时在本小节补充说明。当前阶段以"重启生效"为准，所有 AI 触发敏感度与时间间隔的调整均**只需修改此文件，无需修改任何业务代码**。

---

## 12. 快速启动指南（本地开发）

### 12.1 前置要求

- Node.js 18+（前端）
- Python 3.11+（后端）
- Docker + Docker Compose（数据库）
- Anthropic API Key

### 12.2 启动步骤

> **Docker Compose 使用说明：**
> - **纯数据库模式**（推荐日常开发）：`docker compose up -d` 仅启动 PostgreSQL + Redis + y-websocket，前后端在本地手动启动，支持热重载
> - **全栈容器模式**（推荐集成测试）：使用 `docker-compose.full.yml`，一键启动所有服务，但不支持代码热重载
>
> 以下步骤对应**纯数据库模式**。

1. 克隆仓库并进入项目根目录
2. 复制 `.env.example` 为 `.env`，填写 `ANTHROPIC_API_KEY` 等变量
3. 运行 `docker compose up -d` 启动 PostgreSQL、Redis 与 y-websocket 服务
4. 进入 `backend/` 目录，创建虚拟环境并安装依赖：`pip install -r requirements.txt`
5. 执行数据库迁移：`alembic upgrade head`
6. 启动后端：`uvicorn app.main:app --reload --port 8000`
7. 另开终端，进入 `frontend/` 目录，安装依赖：`npm install`
8. 启动前端：`npm run dev`（默认 `http://localhost:5173`）
9. 浏览器访问 `http://localhost:5173`，注册账号后即可体验

---

*--- 文档结束 ---*

多智能体辅助在线协作学习平台 · 开发文档 v1.2
