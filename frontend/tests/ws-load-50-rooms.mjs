import WebSocket from 'ws'
import { TEST_ACCOUNTS } from './config/testAccounts.js'

const ROOM_COUNT = Math.min(Number(process.env.WS_ROOM_COUNT || 10), 50)
const STUDENTS_PER_ROOM = Number(process.env.WS_STUDENTS_PER_ROOM || 3)
const DURATION_MS = Number(process.env.WS_DURATION_MS || 60000)
const MESSAGE_INTERVAL_MS = Number(process.env.WS_MESSAGE_INTERVAL_MS || 15000)
const MESSAGE_JITTER_MS = Number(process.env.WS_MESSAGE_JITTER_MS || 0)
const MESSAGE_START_STAGGER_MS = Number(process.env.WS_MESSAGE_START_STAGGER_MS || 0)
const MESSAGE_MAX_IN_FLIGHT_PER_CONNECTION = Number(process.env.WS_MESSAGE_MAX_IN_FLIGHT_PER_CONNECTION || 1)
const MESSAGE_BURST = Number(process.env.WS_MESSAGE_BURST || 1)
const MESSAGE_CONTENT_SIZE = Number(process.env.WS_MESSAGE_CONTENT_SIZE || 50)
const WS_EXPECT_BROADCAST = String(process.env.WS_EXPECT_BROADCAST || 'true').toLowerCase() === 'true'
const WS_MESSAGE_TEST_MODE = process.env.WS_MESSAGE_TEST_MODE || 'normal_chat'
const BASE_URL = (process.env.BASE_URL || 'http://localhost:5173').replace(/\/$/, '')
const API_BASE_URL = (process.env.API_BASE_URL || 'http://localhost:8001/api').replace(/\/$/, '')
const RAW_WS_BASE_URL = (process.env.WS_BASE_URL || 'ws://localhost:8001').replace(/\/$/, '')
const ALLOW_REUSE_STUDENT_ACCOUNT = String(process.env.ALLOW_REUSE_STUDENT_ACCOUNT || '').toLowerCase() === 'true'
const AUTO_CREATE_TEST_STUDENTS = String(process.env.AUTO_CREATE_TEST_STUDENTS || 'true').toLowerCase() === 'true'
const AUTO_STUDENT_PASSWORD = process.env.AUTO_TEST_STUDENT_PASSWORD || 'ws_student_password'
const WS_SEND_MESSAGES = String(process.env.WS_SEND_MESSAGES || 'false').toLowerCase() === 'true'

function normalizeWsBaseUrl(raw) {
  if (raw.startsWith('ws://') || raw.startsWith('wss://')) return raw
  if (raw.startsWith('http://')) return raw.replace('http://', 'ws://')
  if (raw.startsWith('https://')) return raw.replace('https://', 'wss://')
  return `ws://${raw}`
}

const WS_BASE_URL = normalizeWsBaseUrl(RAW_WS_BASE_URL)
const WS_MODE = WS_BASE_URL.includes(':5173') ? 'vite-proxy' : 'direct-backend'

const runtime = {
  sockets: new Set(),
  intervalHandles: new Set(),
  timeoutHandles: new Set(),
}

const authHeaders = (token) => ({
  Authorization: `Bearer ${token}`,
  'Content-Type': 'application/json',
})

const stats = {
  totalRooms: ROOM_COUNT,
  targetConnections: ROOM_COUNT * STUDENTS_PER_ROOM,
  openCount: 0,
  authSentCount: 0,
  firstMessageReceivedCount: 0,
  closeCount: 0,
  closeCodeDist: {},
  authCloseCounts: { 4001: 0, 4002: 0, 4003: 0 },
  code1006: 0,
  reconnectCount: 0,
  roomConnectionCount: {},
  perUsernameCloseCodeDist: {},
  perUsernameUseCount: {},
  roomStudentAssignments: {},
  lifetimes: [],
  concentratedDisconnect: false,
  fourSecondPattern: false,
  events: [],
  connectionDetails: [],
  lifetimeBuckets: { lt1s: 0, s1to5: 0, s5to10: 0, gte10: 0 },
  closeSecondBucket: {},
  messageSentSecondBucket: {},
  messageBroadcastSeenSecondBucket: {},
  messagesSent: 0,
  messagesBroadcastSeen: 0,
  messageLatencies: [],
  sentMessageIds: new Set(),
  seenMessageIds: new Set(),
  messageTracking: {},
  closeAround45: [],
  failedRoomIds: new Set(),
  failedUsernames: new Set(),
}

function percentile(arr, p) {
  if (arr.length === 0) return 0
  const sorted = [...arr].sort((a, b) => a - b)
  const idx = Math.min(sorted.length - 1, Math.floor((p / 100) * sorted.length))
  return sorted[idx]
}

function now() {
  return Date.now()
}

function jitterDelay(maxMs) {
  if (!maxMs || maxMs <= 0) return 0
  return Math.floor(Math.random() * (maxMs + 1))
}

function buildMessageContent(base) {
  if (base.length >= MESSAGE_CONTENT_SIZE) return base
  const filler = 'x'.repeat(Math.max(0, MESSAGE_CONTENT_SIZE - base.length))
  return `${base}${filler}`
}

function toWsUrl(baseUrl, roomId) {
  const url = new URL(baseUrl)
  return `${url.protocol}//${url.host}/ws/${roomId}`
}

function updateLifetimeBucket(lifetimeMs) {
  if (lifetimeMs < 1000) stats.lifetimeBuckets.lt1s += 1
  else if (lifetimeMs < 5000) stats.lifetimeBuckets.s1to5 += 1
  else if (lifetimeMs < 10000) stats.lifetimeBuckets.s5to10 += 1
  else stats.lifetimeBuckets.gte10 += 1
}

function closeSecond(startTs, ts) {
  return Math.floor((ts - startTs) / 1000)
}

async function apiPost(url, body, token) {
  const res = await fetch(url, {
    method: 'POST',
    headers: token ? authHeaders(token) : { 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
  })
  const json = await res.json().catch(() => ({}))
  return { ok: res.ok, status: res.status, body: json }
}

async function login(accountType, account) {
  console.log(`[WS-LOAD] login as ${accountType}: ${account.username}`)
  return apiPost(`${API_BASE_URL}/auth/login`, { username: account.username, password: account.password })
}

async function registerStudent(account, index) {
  const body = {
    username: account.username,
    password: account.password,
    display_name: `WS Student ${index + 1}`,
    role: 'student',
  }
  return apiPost(`${API_BASE_URL}/auth/register`, body)
}

async function createRoom(token, index) {
  return apiPost(`${API_BASE_URL}/rooms`, { name: `WS-LOAD-${index}-${Date.now()}` }, token)
}

async function joinRoom(token, roomId) {
  const r = await apiPost(`${API_BASE_URL}/rooms/${roomId}/join`, undefined, token)
  const already = r.status === 409 || String(r.body?.detail || '').includes('已加入')
  return { ...r, ok: r.ok || already }
}

function parseStudentPoolFromEnv() {
  const raw = process.env.TEST_STUDENT_ACCOUNTS
  if (!raw) return null
  try {
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return null
    return parsed
      .map((x) => ({ username: String(x?.username || '').trim(), password: String(x?.password || '').trim() }))
      .filter((x) => x.username && x.password)
  } catch {
    return null
  }
}

function isUsernameExistsResponse(status, body) {
  if (status !== 400) return false
  const detail = String(body?.detail || '')
  return /exists|already|已存在|用户名已存在/i.test(detail)
}

async function resolveStudentPool(targetStudentConnections) {
  const fromEnv = parseStudentPoolFromEnv()
  if (fromEnv && fromEnv.length > 0) {
    return {
      pool: fromEnv,
      source: 'env:TEST_STUDENT_ACCOUNTS',
      registerSummary: {
        requestedCount: 0,
        createdCount: 0,
        reusedExistingCount: 0,
        failedCount: 0,
        sampleUsernames: fromEnv.slice(0, 5).map((x) => x.username),
      },
    }
  }

  const fallback = [{ username: TEST_ACCOUNTS.student.username, password: TEST_ACCOUNTS.student.password }]
  if (!AUTO_CREATE_TEST_STUDENTS) {
    return {
      pool: fallback,
      source: 'default-single-account',
      registerSummary: {
        requestedCount: 0,
        createdCount: 0,
        reusedExistingCount: 0,
        failedCount: 0,
        sampleUsernames: fallback.map((x) => x.username),
      },
    }
  }

  const ts = Date.now()
  const requested = []
  for (let i = 0; i < targetStudentConnections; i += 1) {
    requested.push({ username: `ws_student_${ts}_${i + 1}`, password: AUTO_STUDENT_PASSWORD })
  }

  const created = []
  const reusedExisting = []
  const failed = []

  for (let i = 0; i < requested.length; i += 1) {
    const account = requested[i]
    const r = await registerStudent(account, i)
    if (r.ok) {
      created.push(account)
      continue
    }

    if (isUsernameExistsResponse(r.status, r.body)) {
      const loginRes = await login('student-existing', account)
      if (loginRes.ok) {
        reusedExisting.push(account)
        continue
      }
      failed.push({
        username: account.username,
        status: r.status,
        body: r.body,
        note: `username exists but login failed status=${loginRes.status} body=${JSON.stringify(loginRes.body, null, 2)}`,
      })
      continue
    }

    failed.push({ username: account.username, status: r.status, body: r.body })
  }

  if (failed.length > 0) {
    for (const item of failed.slice(0, 20)) {
      console.log('[WS-LOAD] register failed', {
        username: item.username,
        status: item.status,
        body: JSON.stringify(item.body, null, 2),
        note: item.note || '',
      })
    }
  }

  const pool = [...created, ...reusedExisting]
  const registerSummary = {
    requestedCount: requested.length,
    createdCount: created.length,
    reusedExistingCount: reusedExisting.length,
    failedCount: failed.length,
    sampleUsernames: pool.slice(0, 10).map((x) => x.username),
  }

  console.log('[WS-LOAD] auto register summary', registerSummary)

  if (pool.length === 0) {
    return { pool: fallback, source: 'auto-create-failed-fallback-single', registerSummary }
  }
  return { pool, source: 'auto-created', registerSummary }
}

function pickStudentsForRooms(studentPool, targetStudentConnections) {
  const assignments = []
  let useReuse = false

  if (studentPool.length < targetStudentConnections && !ALLOW_REUSE_STUDENT_ACCOUNT) {
    return {
      ok: false,
      reason:
        `学生账号数量不足，无法模拟真实多学生并发。 pool=${studentPool.length}, ` +
        `target=${targetStudentConnections}, set ALLOW_REUSE_STUDENT_ACCOUNT=true to override`,
      assignments: [],
      useReuse: false,
    }
  }

  for (let idx = 0; idx < targetStudentConnections; idx += 1) {
    if (idx >= studentPool.length) useReuse = true
    assignments.push(studentPool[idx % studentPool.length])
  }

  return { ok: true, assignments, useReuse, reason: '' }
}

function analyzePatterns(startTs, endTs) {
  const closeEvents = stats.events.filter((e) => e.type === 'close').sort((a, b) => a.ts - b.ts)

  const near4Lifetimes = stats.lifetimes.filter((ms) => ms >= 3000 && ms <= 5000)
  stats.fourSecondPattern = near4Lifetimes.length >= Math.max(3, Math.floor(stats.lifetimes.length * 0.2))

  const bucket = {}
  for (const e of closeEvents) {
    const slot = Math.floor((e.ts - startTs) / 1000)
    bucket[slot] = (bucket[slot] || 0) + 1
  }
  const maxPerSecond = Object.values(bucket).reduce((m, v) => Math.max(m, v), 0)
  stats.concentratedDisconnect = maxPerSecond >= Math.max(5, Math.floor(stats.targetConnections * 0.25))

  const messageIdsNear45 = Object.entries(stats.messageTracking)
    .filter(([, v]) => {
      const sec = Math.floor((v.sendAt - startTs) / 1000)
      return sec >= 35 && sec <= 55
    })
    .map(([id, v]) => ({
      messageId: id,
      roomId: v.roomId,
      username: v.username,
      sendAtSec: Math.floor((v.sendAt - startTs) / 1000),
      seenAtSec: v.seenAt ? Math.floor((v.seenAt - startTs) / 1000) : null,
      seenCount: v.seenCount,
    }))

  return {
    durationMs: endTs - startTs,
    openEvents: stats.events.filter((e) => e.type === 'open').length,
    closeEvents: closeEvents.length,
    maxClosePerSecond: maxPerSecond,
    messageIdsNear45Sample: messageIdsNear45.slice(0, 60),
  }
}

function printSummary(extra, setupMeta) {
  const p50 = percentile(stats.lifetimes, 50)
  const p95 = percentile(stats.lifetimes, 95)
  const min = stats.lifetimes.length ? Math.min(...stats.lifetimes) : 0
  const max = stats.lifetimes.length ? Math.max(...stats.lifetimes) : 0
  const openRate = stats.targetConnections ? stats.openCount / stats.targetConnections : 0
  const code1006Rate = stats.targetConnections ? stats.code1006 / stats.targetConnections : 0
  const aliveAtEnd = Object.values(stats.roomConnectionCount).reduce((sum, item) => sum + (item.openAliveAtEnd || 0), 0)
  const aliveAfter5s = stats.connectionDetails.filter((d) => d.aliveAfter5s).length
  const aliveAfter10s = stats.connectionDetails.filter((d) => d.aliveAfter10s).length
  const messageSuccessRate = stats.messagesSent ? stats.messagesBroadcastSeen / stats.messagesSent : 0
  const latencyP50 = percentile(stats.messageLatencies, 50)
  const latencyP95 = percentile(stats.messageLatencies, 95)
  const latencyP99 = percentile(stats.messageLatencies, 99)
  const latencyMax = stats.messageLatencies.length ? Math.max(...stats.messageLatencies) : 0

  const roomHealth = Object.fromEntries(Object.entries(stats.roomConnectionCount).map(([roomId, v]) => [roomId, v.openAliveAtEnd]))
  const allRoomsHaveSurvivor = Object.values(roomHealth).every((v) => v >= 1)

  const pass =
    openRate >= 0.95 &&
    stats.authCloseCounts[4001] === 0 &&
    stats.authCloseCounts[4002] === 0 &&
    stats.authCloseCounts[4003] === 0 &&
    code1006Rate < 0.01 &&
    allRoomsHaveSurvivor &&
    !stats.fourSecondPattern

  console.log('[WS-LOAD] summary', {
    mode: WS_MODE,
    wsBaseUrl: WS_BASE_URL,
    wsUrlSample: Object.keys(stats.roomStudentAssignments).length
      ? toWsUrl(WS_BASE_URL, Object.keys(stats.roomStudentAssignments)[0])
      : '(none)',
    wsSendMessages: WS_SEND_MESSAGES,
    totalRooms: stats.totalRooms,
    targetConnections: stats.targetConnections,
    openCount: stats.openCount,
    openRate,
    authSentCount: stats.authSentCount,
    firstMessageReceivedCount: stats.firstMessageReceivedCount,
    aliveAfter5s,
    aliveAfter10s,
    aliveAtEnd,
    closeCount: stats.closeCount,
    closeCodeDist: stats.closeCodeDist,
    authCloseCounts: stats.authCloseCounts,
    code1006: stats.code1006,
    reconnectCount: stats.reconnectCount,
    perRoom: stats.roomConnectionCount,
    byRoomId: stats.roomConnectionCount,
    byUsernameCloseCodeDist: stats.perUsernameCloseCodeDist,
    byCloseSecondBucket: stats.closeSecondBucket,
    byMessageSentSecondBucket: stats.messageSentSecondBucket,
    byMessageBroadcastSeenSecondBucket: stats.messageBroadcastSeenSecondBucket,
    byLifetimeBucket: stats.lifetimeBuckets,
    messagesSent: stats.messagesSent,
    messagesBroadcastSeen: stats.messagesBroadcastSeen,
    messageBroadcastSuccessRate: messageSuccessRate,
    messageLatencyMs: { p50: latencyP50, p95: latencyP95, p99: latencyP99, max: latencyMax },
    lifetimeMs: { p50, p95, min, max },
    concentratedDisconnect: stats.concentratedDisconnect,
    fourSecondPattern: stats.fourSecondPattern,
    allRoomsHaveSurvivor,
    singleStudentReuseWarning: setupMeta.singleStudentReuseWarning,
    studentPoolSource: setupMeta.studentPoolSource,
    studentPoolSize: setupMeta.studentPoolSize,
    targetStudentConnections: setupMeta.targetStudentConnections,
    reuseEnabled: setupMeta.reuseEnabled,
    registerSummary: setupMeta.registerSummary,
    perUsernameUseCount: stats.perUsernameUseCount,
    roomStudentAssignments: stats.roomStudentAssignments,
    connectionDetailsSample: stats.connectionDetails.slice(0, 20),
    closeAround45Sample: stats.closeAround45.slice(0, 30),
    failedRoomIds: [...stats.failedRoomIds],
    failedUsernames: [...stats.failedUsernames],
    extra,
    result: pass ? 'PASS' : 'FAIL',
  })

  if (!pass) process.exitCode = 1
}

function trackInterval(handle) {
  runtime.intervalHandles.add(handle)
  return handle
}

function trackTimeout(handle) {
  runtime.timeoutHandles.add(handle)
  return handle
}

function clearTrackedInterval(handle) {
  if (handle) {
    clearInterval(handle)
    runtime.intervalHandles.delete(handle)
  }
}

function clearTrackedTimeout(handle) {
  if (handle) {
    clearTimeout(handle)
    runtime.timeoutHandles.delete(handle)
  }
}

function cleanupRuntime() {
  for (const h of runtime.intervalHandles) clearInterval(h)
  runtime.intervalHandles.clear()

  for (const h of runtime.timeoutHandles) clearTimeout(h)
  runtime.timeoutHandles.clear()

  for (const ws of runtime.sockets) {
    try {
      if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) {
        ws.close(1000, 'cleanup')
      }
      ws.removeAllListeners()
    } catch {
      // ignore
    }
  }
  runtime.sockets.clear()
}

async function main() {
  console.log('[WS-LOAD] config', {
    ROOM_COUNT,
    STUDENTS_PER_ROOM,
    DURATION_MS,
    MESSAGE_INTERVAL_MS,
    MESSAGE_JITTER_MS,
    MESSAGE_START_STAGGER_MS,
    MESSAGE_MAX_IN_FLIGHT_PER_CONNECTION,
    MESSAGE_BURST,
    MESSAGE_CONTENT_SIZE,
    WS_EXPECT_BROADCAST,
    WS_MESSAGE_TEST_MODE,
    BASE_URL,
    API_BASE_URL,
    WS_BASE_URL,
    WS_MODE,
    WS_SEND_MESSAGES,
    ALLOW_REUSE_STUDENT_ACCOUNT,
    AUTO_CREATE_TEST_STUDENTS,
  })

  const targetStudentConnections = ROOM_COUNT * STUDENTS_PER_ROOM
  const teacherLogin = await login('teacher', TEST_ACCOUNTS.teacher)
  if (!teacherLogin.ok) {
    throw new Error(`teacher login failed status=${teacherLogin.status} body=${JSON.stringify(teacherLogin.body)}`)
  }
  const teacherToken = teacherLogin.body.access_token

  const poolResolved = await resolveStudentPool(targetStudentConnections)
  const studentPool = poolResolved.pool
  const allocation = pickStudentsForRooms(studentPool, targetStudentConnections)

  if (!allocation.ok) {
    console.log('[WS-LOAD] test setup failure', {
      source: poolResolved.source,
      allowReuse: ALLOW_REUSE_STUDENT_ACCOUNT,
      studentPoolSize: studentPool.length,
      targetStudentConnections,
      reason: allocation.reason,
    })
    throw new Error(allocation.reason)
  }

  if (studentPool.length === 1 && targetStudentConnections > 1) {
    console.log('[WS-LOAD][WARN] 当前使用单学生账号模拟多学生连接，结果可能不代表真实并发能力。')
  }
  if (allocation.useReuse) {
    console.log('[WS-LOAD][WARN] 学生账号池不足，已开启账号复用模式。')
  }

  const studentTokenByUsername = {}
  for (const student of studentPool) {
    const loginRes = await login('student', student)
    if (!loginRes.ok) {
      throw new Error(`student login failed username=${student.username} status=${loginRes.status} body=${JSON.stringify(loginRes.body)}`)
    }
    studentTokenByUsername[student.username] = loginRes.body.access_token
    stats.perUsernameCloseCodeDist[student.username] = {}
    stats.perUsernameUseCount[student.username] = 0
  }

  const roomIds = []
  const studentAssignmentsFlat = allocation.assignments
  let assignmentCursor = 0

  for (let i = 0; i < ROOM_COUNT; i += 1) {
    const created = await createRoom(teacherToken, i + 1)
    if (!created.ok) {
      throw new Error(`create room failed idx=${i} status=${created.status} body=${JSON.stringify(created.body)}`)
    }
    const roomId = String(created.body.id)
    roomIds.push(roomId)
    stats.roomConnectionCount[roomId] = { target: STUDENTS_PER_ROOM, opened: 0, openAliveAtEnd: 0 }

    const teacherJoin = await joinRoom(teacherToken, roomId)
    if (!teacherJoin.ok) {
      throw new Error(`teacher join failed room=${roomId} status=${teacherJoin.status} body=${JSON.stringify(teacherJoin.body)}`)
    }

    const assignedStudents = []
    for (let k = 0; k < STUDENTS_PER_ROOM; k += 1) {
      const student = studentAssignmentsFlat[assignmentCursor]
      assignmentCursor += 1
      assignedStudents.push(student)
      stats.perUsernameUseCount[student.username] += 1
      const token = studentTokenByUsername[student.username]
      const studentJoin = await joinRoom(token, roomId)
      if (!studentJoin.ok) {
        console.log(`[WS-LOAD] student join failed room=${roomId} username=${student.username} status=${studentJoin.status} body=${JSON.stringify(studentJoin.body)}`)
        if (studentJoin.status === 403) {
          console.log('[WS-LOAD] Student account lacks permission for room join in current setup.')
        }
        throw new Error(`student join failed room=${roomId} username=${student.username}`)
      }
    }
    stats.roomStudentAssignments[roomId] = assignedStudents.map((s) => s.username)
  }

  const connections = []
  const startTs = now()
  const endTs = startTs + DURATION_MS

  for (const roomId of roomIds) {
    for (let i = 0; i < STUDENTS_PER_ROOM; i += 1) {
      const studentUsername = stats.roomStudentAssignments[roomId][i]
      const studentToken = studentTokenByUsername[studentUsername]
      const wsUrl = toWsUrl(WS_BASE_URL, roomId)
      const connId = `${roomId}-${i}-${now()}`
      const detail = {
        roomId,
        username: studentUsername,
        connectionId: connId,
        createdAt: now(),
        openAt: null,
        authSentAt: null,
        firstMessageAt: null,
        lastMessageAt: null,
        closeAt: null,
        closeCode: null,
        closeReason: '',
        lifetimeMs: null,
        aliveAfter5s: false,
        aliveAfter10s: false,
        aliveAtEnd: false,
        reconnects: 0,
      }
      stats.connectionDetails.push(detail)

      const conn = {
        id: connId,
        roomId,
        studentUsername,
        wsUrl,
        detail,
        ws: null,
        timer: null,
        alive5Handle: null,
        alive10Handle: null,
        seq: 0,
        inFlight: 0,
        messageStartHandle: null,
      }

      const connect = () => {
        conn.ws = new WebSocket(wsUrl)
        runtime.sockets.add(conn.ws)
        detail.createdAt = now()

        conn.ws.on('open', () => {
          detail.openAt = now()
          stats.openCount += 1
          stats.roomConnectionCount[roomId].opened += 1
          stats.events.push({ type: 'open', ts: now(), roomId, connId })

          const authPayload = JSON.stringify({ type: 'auth', token: studentToken })
          conn.ws.send(authPayload)
          detail.authSentAt = now()
          stats.authSentCount += 1

          const sendPresenceAndMessages = () => {
            if (!conn.ws || conn.ws.readyState !== WebSocket.OPEN) return
            const sendTs = now()
            const sec = closeSecond(startTs, sendTs)
            const presencePayload = JSON.stringify({ type: 'presence:ping', ts: sendTs, room_id: roomId })
            conn.ws.send(presencePayload)

            if (!WS_SEND_MESSAGES) return
            if (conn.inFlight >= MESSAGE_MAX_IN_FLIGHT_PER_CONNECTION) return
            for (let burst = 0; burst < MESSAGE_BURST; burst += 1) {
              if (conn.inFlight >= MESSAGE_MAX_IN_FLIGHT_PER_CONNECTION) break
              conn.seq += 1
              const messageId = `loadmsg:${roomId}:${studentUsername}:${conn.seq}:${now()}`
              const content = buildMessageContent(`${messageId} mode=${WS_MESSAGE_TEST_MODE}`)
              const payload = JSON.stringify({
                type: 'chat:message',
                content,
                mentions: [],
              })
              conn.ws.send(payload)
              conn.inFlight += 1
              stats.messagesSent += 1
              stats.sentMessageIds.add(messageId)
              stats.messageSentSecondBucket[sec] = (stats.messageSentSecondBucket[sec] || 0) + 1
              stats.messageTracking[messageId] = {
                roomId,
                username: studentUsername,
                connectionId: connId,
                sendAt: now(),
                seenAt: null,
                seenCount: 0,
              }
            }
          }

          const scheduleTicker = () => {
            conn.timer = trackInterval(
              setInterval(() => {
                const run = () => sendPresenceAndMessages()
                const jitter = jitterDelay(MESSAGE_JITTER_MS)
                if (jitter > 0) {
                  const h = trackTimeout(
                    setTimeout(() => {
                      clearTrackedTimeout(h)
                      run()
                    }, jitter)
                  )
                } else {
                  run()
                }
              }, MESSAGE_INTERVAL_MS)
            )
          }

          const startStagger = jitterDelay(MESSAGE_START_STAGGER_MS)
          if (startStagger > 0) {
            conn.messageStartHandle = trackTimeout(
              setTimeout(() => {
                clearTrackedTimeout(conn.messageStartHandle)
                conn.messageStartHandle = null
                sendPresenceAndMessages()
                if (MESSAGE_INTERVAL_MS > 0) scheduleTicker()
              }, startStagger)
            )
          } else {
            sendPresenceAndMessages()
            if (MESSAGE_INTERVAL_MS > 0) scheduleTicker()
          }

          conn.alive5Handle = trackTimeout(
            setTimeout(() => {
              clearTrackedTimeout(conn.alive5Handle)
              if (conn.ws && conn.ws.readyState === WebSocket.OPEN) detail.aliveAfter5s = true
            }, 5000)
          )

          conn.alive10Handle = trackTimeout(
            setTimeout(() => {
              clearTrackedTimeout(conn.alive10Handle)
              if (conn.ws && conn.ws.readyState === WebSocket.OPEN) detail.aliveAfter10s = true
            }, 10000)
          )
        })

        conn.ws.on('message', (raw) => {
          const recvTs = now()
          if (!detail.firstMessageAt) {
            detail.firstMessageAt = recvTs
            stats.firstMessageReceivedCount += 1
          }
          detail.lastMessageAt = recvTs
          const text = String(raw || '')
          const sec = closeSecond(startTs, recvTs)
          let payload = null
          try {
            payload = JSON.parse(text)
          } catch {
            payload = null
          }
          if (payload && payload.type === 'chat:new_message' && typeof payload.content === 'string' && payload.content.includes('loadmsg:')) {
            const match = payload.content.match(/loadmsg:[^\s]+/)
            const messageId = match ? match[0] : null
            if (messageId && stats.messageTracking[messageId]) {
              const entry = stats.messageTracking[messageId]
              entry.seenCount += 1
              if (!entry.seenAt) {
                entry.seenAt = recvTs
                const latency = recvTs - entry.sendAt
                stats.messageLatencies.push(latency)
                stats.messagesBroadcastSeen += 1
                stats.seenMessageIds.add(messageId)
                stats.messageBroadcastSeenSecondBucket[sec] = (stats.messageBroadcastSeenSecondBucket[sec] || 0) + 1
              }
              entry.lastSeenByConnectionAt = recvTs
              if (conn.inFlight > 0) conn.inFlight -= 1
            }
          }
          stats.events.push({ type: 'message', ts: recvTs, roomId, connId, sample: text.slice(0, 120) })
        })

        conn.ws.on('close', (code, reasonBuffer) => {
          const closeTs = now()
          detail.closeAt = closeTs
          detail.closeCode = Number(code)
          detail.closeReason = String(reasonBuffer || '')
          detail.lifetimeMs = detail.openAt ? closeTs - detail.openAt : 0
          if (detail.openAt) {
            stats.lifetimes.push(detail.lifetimeMs)
            updateLifetimeBucket(detail.lifetimeMs)
          }

          clearTrackedInterval(conn.timer)
          clearTrackedTimeout(conn.messageStartHandle)
          clearTrackedTimeout(conn.alive5Handle)
          clearTrackedTimeout(conn.alive10Handle)
          conn.timer = null
          conn.messageStartHandle = null
          conn.alive5Handle = null
          conn.alive10Handle = null
          if (conn.ws) runtime.sockets.delete(conn.ws)

          stats.closeCount += 1
          stats.closeCodeDist[detail.closeCode] = (stats.closeCodeDist[detail.closeCode] || 0) + 1
          stats.perUsernameCloseCodeDist[studentUsername][detail.closeCode] =
            (stats.perUsernameCloseCodeDist[studentUsername][detail.closeCode] || 0) + 1
          if (detail.closeCode === 1006) stats.code1006 += 1
          if ([4001, 4002, 4003].includes(detail.closeCode)) {
            stats.authCloseCounts[detail.closeCode] += 1
          }

          const sec = closeSecond(startTs, closeTs)
          stats.closeSecondBucket[sec] = (stats.closeSecondBucket[sec] || 0) + 1
          if (detail.closeCode === 1006) {
            stats.failedRoomIds.add(roomId)
            stats.failedUsernames.add(studentUsername)
          }
          if (sec >= 40 && sec <= 50) {
            stats.closeAround45.push({
              roomId,
              username: studentUsername,
              connectionId: connId,
              sec,
              closeCode: detail.closeCode,
              lastMessageAt: detail.lastMessageAt,
            })
          }

          stats.events.push({ type: 'close', ts: closeTs, roomId, connId, code: detail.closeCode, reason: detail.closeReason })

          if (closeTs < endTs && detail.reconnects < 1 && detail.closeCode !== 1000) {
            detail.reconnects += 1
            stats.reconnectCount += 1
            const h = trackTimeout(
              setTimeout(() => {
                clearTrackedTimeout(h)
                connect()
              }, 1000)
            )
          }
        })

        conn.ws.on('error', (error) => {
          stats.events.push({ type: 'error', ts: now(), roomId, connId, error: String(error?.message || error) })
        })
      }

      connect()
      connections.push(conn)
    }
  }

  await new Promise((resolve) => setTimeout(resolve, DURATION_MS))

  for (const conn of connections) {
    const isOpen = conn.ws && conn.ws.readyState === WebSocket.OPEN
    if (isOpen) {
      stats.roomConnectionCount[conn.roomId].openAliveAtEnd += 1
      conn.detail.aliveAtEnd = true
      if (conn.detail.openAt && conn.detail.lifetimeMs == null) {
        const lived = now() - conn.detail.openAt
        stats.lifetimes.push(lived)
        updateLifetimeBucket(lived)
        conn.detail.lifetimeMs = lived
      }
    }
    clearTrackedInterval(conn.timer)
    clearTrackedTimeout(conn.messageStartHandle)
    clearTrackedTimeout(conn.alive5Handle)
    clearTrackedTimeout(conn.alive10Handle)
    conn.timer = null
    conn.alive5Handle = null
    conn.alive10Handle = null
    try {
      conn.ws?.close(1000, 'load-test-end')
    } catch {
      // ignore
    }
  }

  const extra = analyzePatterns(startTs, now())

  if (stats.openCount < stats.targetConnections) {
    console.log(
      `[WS-LOAD] Open count below target (${stats.openCount}/${stats.targetConnections}). ` +
        'This may indicate account/session limits or room permission setup issues.'
    )
  }

  printSummary(extra, {
    singleStudentReuseWarning: studentPool.length === 1 && targetStudentConnections > 1,
    studentPoolSource: poolResolved.source,
    studentPoolSize: studentPool.length,
    targetStudentConnections,
    reuseEnabled: allocation.useReuse,
    registerSummary: poolResolved.registerSummary,
  })
}

main()
  .catch((err) => {
    console.error('[WS-LOAD] fatal', err)
    process.exitCode = 1
  })
  .finally(() => {
    cleanupRuntime()
  })
