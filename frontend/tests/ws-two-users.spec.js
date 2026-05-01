import { test, expect } from '@playwright/test'
import { TEST_ACCOUNTS } from './config/testAccounts.js'

function hasFourSecondPattern(timestamps) {
  if (timestamps.length < 4) return false
  const intervals = []
  for (let i = 1; i < timestamps.length; i += 1) {
    intervals.push((timestamps[i] - timestamps[i - 1]) / 1000)
  }
  const nearFour = intervals.filter((v) => v >= 3 && v <= 5)
  return nearFour.length >= 2
}

async function loginWithAccount(apiBase, request, accountType, account) {
  console.log(`[WS-2U] Using test account: ${accountType} / ${account.username}`)
  const resp = await request.post(`${apiBase}/auth/login`, {
    data: { username: account.username, password: account.password },
  })
  const body = await resp.json().catch(() => ({}))
  return {
    ok: resp.ok() && Boolean(body?.access_token && body?.user),
    status: resp.status(),
    token: body?.access_token,
    user: body?.user,
    accountType,
    username: account.username,
    body,
  }
}

async function createRoom(apiBase, request, token) {
  const roomName = `WS-2U-${Date.now()}`
  const resp = await request.post(`${apiBase}/rooms`, {
    headers: { Authorization: `Bearer ${token}` },
    data: { name: roomName },
  })
  const body = await resp.json().catch(() => ({}))
  return { ok: resp.ok(), status: resp.status(), body }
}

async function joinRoom(apiBase, request, token, roomId, who) {
  const url = `${apiBase}/rooms/${roomId}/join`
  const resp = await request.post(url, {
    headers: { Authorization: `Bearer ${token}` },
  })
  const body = await resp.json().catch(() => ({}))
  const already = resp.status() === 409 || String(body?.detail || '').includes('已加入')
  const ok = resp.status() === 200 || already
  return { ok, status: resp.status(), body, url, who }
}

function attachPageDiagnostics(page, roomId, label, store) {
  page.on('console', (msg) => {
    const t = msg.type()
    const txt = msg.text()
    const hitKeyword = /(WS-Debug|WebSocket|auth|token|router)/i.test(txt)
    if (t === 'error' || t === 'warning' || hitKeyword) {
      console.log(`[${label}][Console][${t}] ${txt}`)
    }
  })

  page.on('pageerror', (error) => {
    console.log(`[${label}][PageError]`, String(error))
  })

  page.on('response', (resp) => {
    const url = resp.url()
    const status = resp.status()
    const hit =
      url.includes('/api/auth/login') ||
      url.includes('/api/rooms') ||
      (roomId && url.includes(`/api/rooms/${roomId}`))
    if (hit) {
      store.apiResponses.push({ status, url })
      console.log(`[${label}][HTTP]`, status, url)
    }
  })

  page.on('websocket', (ws) => {
    const createdAt = Date.now()
    const url = ws.url()
    const item = {
      url,
      createdAt,
      closedAt: null,
      closeCode: null,
      closeReason: '',
      lifetimeMs: null,
    }
    store.events.push(item)

    ws.on('close', () => {
      item.closedAt = Date.now()
      item.lifetimeMs = item.closedAt - item.createdAt
    })

    ws.on('framereceived', (event) => {
      const payload = String(event.payload || '')
      if (payload.includes('"type":"agent:mention_blocked"')) return
    })
  })
}

function summarizeSide(store, roomId) {
  const roomSockets = store.events.filter((e) => e.url.includes(`/ws/${roomId}`))
  const createdTimes = roomSockets.map((e) => e.createdAt).sort((a, b) => a - b)
  const periodicReconnect = hasFourSecondPattern(createdTimes)
  const maxLifetimeMs = roomSockets.reduce((acc, e) => {
    const end = e.closedAt ?? Date.now()
    const lived = end - e.createdAt
    return Math.max(acc, lived)
  }, 0)
  const closeDetails = roomSockets.map((e) => ({
    url: e.url,
    createdAt: e.createdAt,
    closedAt: e.closedAt,
    lifetimeMs: (e.closedAt ?? Date.now()) - e.createdAt,
    closeCode: e.closeCode,
    closeReason: e.closeReason,
  }))

  return {
    roomSockets,
    count: roomSockets.length,
    periodicReconnect,
    hasLongLived: maxLifetimeMs >= 10000,
    maxLifetimeMs,
    closeDetails,
  }
}

test('two-user websocket stability in same room (30s)', async ({ browser, request, baseURL }) => {
  const targetBase = baseURL || process.env.BASE_URL || 'http://localhost:5173'
  const apiBase = `${targetBase.replace(/\/$/, '')}/api`

  const teacherLogin = await loginWithAccount(apiBase, request, 'teacher', TEST_ACCOUNTS.teacher)
  expect(teacherLogin.ok, `teacher login failed status=${teacherLogin.status} body=${JSON.stringify(teacherLogin.body)}`).toBe(true)

  const create = await createRoom(apiBase, request, teacherLogin.token)
  expect(create.ok, `create room failed status=${create.status} body=${JSON.stringify(create.body)}`).toBe(true)
  const roomId = String(create.body.id)

  const teacherJoin = await joinRoom(apiBase, request, teacherLogin.token, roomId, 'teacher')
  if (!teacherJoin.ok && teacherJoin.status === 403) {
    throw new Error(
      `Test setup failure: teacher cannot join room. status=${teacherJoin.status} url=${teacherJoin.url} body=${JSON.stringify(teacherJoin.body)}`
    )
  }
  expect(teacherJoin.ok, `teacher join failed status=${teacherJoin.status} body=${JSON.stringify(teacherJoin.body)}`).toBe(true)

  const studentLogin = await loginWithAccount(apiBase, request, 'student', TEST_ACCOUNTS.student)
  expect(studentLogin.ok, `student login failed status=${studentLogin.status} body=${JSON.stringify(studentLogin.body)}`).toBe(true)

  const studentJoin = await joinRoom(apiBase, request, studentLogin.token, roomId, 'student')
  if (!studentJoin.ok && studentJoin.status === 403) {
    throw new Error(
      `Test setup failure: student cannot join room. status=${studentJoin.status} url=${studentJoin.url} body=${JSON.stringify(studentJoin.body)}`
    )
  }
  expect(studentJoin.ok, `student join failed status=${studentJoin.status} body=${JSON.stringify(studentJoin.body)}`).toBe(true)

  const teacherContext = await browser.newContext()
  const studentContext = await browser.newContext()
  const teacherPage = await teacherContext.newPage()
  const studentPage = await studentContext.newPage()

  const teacherStore = { events: [], apiResponses: [] }
  const studentStore = { events: [], apiResponses: [] }
  attachPageDiagnostics(teacherPage, roomId, 'teacher', teacherStore)
  attachPageDiagnostics(studentPage, roomId, 'student', studentStore)

  await teacherPage.addInitScript(
    ({ token, user }) => {
      window.localStorage.setItem('token', token)
      window.localStorage.setItem('user', JSON.stringify(user))
    },
    { token: teacherLogin.token, user: teacherLogin.user }
  )

  await studentPage.addInitScript(
    ({ token, user }) => {
      window.localStorage.setItem('token', token)
      window.localStorage.setItem('user', JSON.stringify(user))
    },
    { token: studentLogin.token, user: studentLogin.user }
  )

  const roomUrl = `${targetBase}/room/${roomId}`
  await Promise.all([
    teacherPage.goto(roomUrl, { waitUntil: 'domcontentloaded' }),
    studentPage.goto(roomUrl, { waitUntil: 'domcontentloaded' }),
  ])

  await Promise.all([teacherPage.waitForTimeout(30000), studentPage.waitForTimeout(30000)])

  const teacherSummary = summarizeSide(teacherStore, roomId)
  const studentSummary = summarizeSide(studentStore, roomId)

  const teacherAuthClose = teacherSummary.closeDetails.find((d) => [4001, 4002, 4003].includes(Number(d.closeCode)))
  const studentAuthClose = studentSummary.closeDetails.find((d) => [4001, 4002, 4003].includes(Number(d.closeCode)))

  console.log('[WS-2U] summary', {
    roomId,
    teacherLoginStatus: teacherLogin.status,
    studentLoginStatus: studentLogin.status,
    teacherJoinStatus: teacherJoin.status,
    studentJoinStatus: studentJoin.status,
    teacherWsCount: teacherSummary.count,
    teacherPeriodicReconnect: teacherSummary.periodicReconnect,
    teacherMaxLifetimeMs: teacherSummary.maxLifetimeMs,
    teacherCloseDetails: teacherSummary.closeDetails,
    studentWsCount: studentSummary.count,
    studentPeriodicReconnect: studentSummary.periodicReconnect,
    studentMaxLifetimeMs: studentSummary.maxLifetimeMs,
    studentCloseDetails: studentSummary.closeDetails,
    teacherAuthClose,
    studentAuthClose,
  })

  expect(teacherSummary.count, `teacher room websocket count should be <=2, got ${teacherSummary.count}`).toBeLessThanOrEqual(2)
  expect(studentSummary.count, `student room websocket count should be <=2, got ${studentSummary.count}`).toBeLessThanOrEqual(2)
  expect(teacherSummary.periodicReconnect, 'teacher has roughly 4-second reconnect cycle').toBe(false)
  expect(studentSummary.periodicReconnect, 'student has roughly 4-second reconnect cycle').toBe(false)
  expect(teacherSummary.hasLongLived, 'teacher has no websocket alive >10s').toBe(true)
  expect(studentSummary.hasLongLived, 'student has no websocket alive >10s').toBe(true)
  expect(Boolean(teacherAuthClose), `teacher got auth close: ${JSON.stringify(teacherAuthClose)}`).toBe(false)
  expect(Boolean(studentAuthClose), `student got auth close: ${JSON.stringify(studentAuthClose)}`).toBe(false)

  await teacherContext.close()
  await studentContext.close()
})
