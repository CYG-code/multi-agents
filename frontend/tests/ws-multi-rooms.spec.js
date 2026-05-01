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
  console.log(`[WS-MR] Using test account: ${accountType} / ${account.username}`)
  const resp = await request.post(`${apiBase}/auth/login`, {
    data: { username: account.username, password: account.password },
  })
  const body = await resp.json().catch(() => ({}))
  return {
    ok: resp.ok() && Boolean(body?.access_token && body?.user),
    status: resp.status(),
    token: body?.access_token,
    user: body?.user,
    body,
  }
}

async function createRoom(apiBase, request, token, index) {
  const roomName = `WS-MR-${index}-${Date.now()}`
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
  })
}

function summarizeSide(store, roomId) {
  const roomSockets = store.events.filter((e) => e.url.includes(`/ws/${roomId}`))
  const createdTimes = roomSockets.map((e) => e.createdAt).sort((a, b) => a - b)
  const periodicReconnect = hasFourSecondPattern(createdTimes)
  const maxLifetimeMs = roomSockets.reduce((acc, e) => {
    const end = e.closedAt ?? Date.now()
    return Math.max(acc, end - e.createdAt)
  }, 0)
  const closeDetails = roomSockets.map((e) => ({
    url: e.url,
    createdAt: e.createdAt,
    closedAt: e.closedAt,
    lifetimeMs: (e.closedAt ?? Date.now()) - e.createdAt,
    closeCode: e.closeCode,
    closeReason: e.closeReason,
  }))
  const authClose = closeDetails.find((d) => [4001, 4002, 4003].includes(Number(d.closeCode)))

  return {
    count: roomSockets.length,
    periodicReconnect,
    maxLifetimeMs,
    hasLongLived: maxLifetimeMs >= 10000,
    closeDetails,
    authClose,
  }
}

test('multi-room websocket stability with teacher and student (3 rooms, 30s)', async ({ browser, request, baseURL }) => {
  const targetBase = baseURL || process.env.BASE_URL || 'http://localhost:5173'
  const apiBase = `${targetBase.replace(/\/$/, '')}/api`

  const teacherLogin = await loginWithAccount(apiBase, request, 'teacher', TEST_ACCOUNTS.teacher)
  expect(teacherLogin.ok, `teacher login failed status=${teacherLogin.status} body=${JSON.stringify(teacherLogin.body)}`).toBe(true)

  const studentLogin = await loginWithAccount(apiBase, request, 'student', TEST_ACCOUNTS.student)
  expect(studentLogin.ok, `student login failed status=${studentLogin.status} body=${JSON.stringify(studentLogin.body)}`).toBe(true)

  const roomSetups = []
  for (let i = 0; i < 3; i += 1) {
    const created = await createRoom(apiBase, request, teacherLogin.token, i + 1)
    expect(created.ok, `create room[${i}] failed status=${created.status} body=${JSON.stringify(created.body)}`).toBe(true)
    const roomId = String(created.body.id)

    const teacherJoin = await joinRoom(apiBase, request, teacherLogin.token, roomId, 'teacher')
    expect(teacherJoin.ok, `teacher join room[${i}] failed status=${teacherJoin.status} body=${JSON.stringify(teacherJoin.body)}`).toBe(true)

    const studentJoin = await joinRoom(apiBase, request, studentLogin.token, roomId, 'student')
    expect(studentJoin.ok, `student join room[${i}] failed status=${studentJoin.status} body=${JSON.stringify(studentJoin.body)}`).toBe(true)

    roomSetups.push({ roomId, createStatus: created.status, teacherJoinStatus: teacherJoin.status, studentJoinStatus: studentJoin.status })
  }

  const actors = []
  for (const setup of roomSetups) {
    const teacherContext = await browser.newContext()
    const studentContext = await browser.newContext()
    const teacherPage = await teacherContext.newPage()
    const studentPage = await studentContext.newPage()
    const teacherStore = { events: [], apiResponses: [] }
    const studentStore = { events: [], apiResponses: [] }

    attachPageDiagnostics(teacherPage, setup.roomId, `room-${setup.roomId}-teacher`, teacherStore)
    attachPageDiagnostics(studentPage, setup.roomId, `room-${setup.roomId}-student`, studentStore)

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

    const roomUrl = `${targetBase}/room/${setup.roomId}`
    await Promise.all([
      teacherPage.goto(roomUrl, { waitUntil: 'domcontentloaded' }),
      studentPage.goto(roomUrl, { waitUntil: 'domcontentloaded' }),
    ])

    actors.push({
      roomId: setup.roomId,
      teacherContext,
      studentContext,
      teacherPage,
      studentPage,
      teacherStore,
      studentStore,
    })
  }

  await Promise.all(
    actors.flatMap((a) => [a.teacherPage.waitForTimeout(30000), a.studentPage.waitForTimeout(30000)])
  )

  const summaries = actors.map((a) => {
    const teacher = summarizeSide(a.teacherStore, a.roomId)
    const student = summarizeSide(a.studentStore, a.roomId)
    return {
      roomId: a.roomId,
      teacher,
      student,
    }
  })

  console.log('[WS-MR] summary', {
    teacherLoginStatus: teacherLogin.status,
    studentLoginStatus: studentLogin.status,
    rooms: summaries.map((s) => ({
      roomId: s.roomId,
      teacherWsCount: s.teacher.count,
      teacherMaxLifetimeMs: s.teacher.maxLifetimeMs,
      teacherPeriodicReconnect: s.teacher.periodicReconnect,
      teacherAuthClose: s.teacher.authClose,
      teacherCloseDetails: s.teacher.closeDetails,
      studentWsCount: s.student.count,
      studentMaxLifetimeMs: s.student.maxLifetimeMs,
      studentPeriodicReconnect: s.student.periodicReconnect,
      studentAuthClose: s.student.authClose,
      studentCloseDetails: s.student.closeDetails,
    })),
  })

  for (const s of summaries) {
    expect(s.teacher.count, `teacher ws count >2 in room ${s.roomId}, got ${s.teacher.count}`).toBeLessThanOrEqual(2)
    expect(s.student.count, `student ws count >2 in room ${s.roomId}, got ${s.student.count}`).toBeLessThanOrEqual(2)
    expect(s.teacher.hasLongLived, `teacher no ws alive >10s in room ${s.roomId}`).toBe(true)
    expect(s.student.hasLongLived, `student no ws alive >10s in room ${s.roomId}`).toBe(true)
    expect(s.teacher.periodicReconnect, `teacher has ~4s reconnect cycle in room ${s.roomId}`).toBe(false)
    expect(s.student.periodicReconnect, `student has ~4s reconnect cycle in room ${s.roomId}`).toBe(false)
    expect(Boolean(s.teacher.authClose), `teacher got auth close in room ${s.roomId}: ${JSON.stringify(s.teacher.authClose)}`).toBe(false)
    expect(Boolean(s.student.authClose), `student got auth close in room ${s.roomId}: ${JSON.stringify(s.student.authClose)}`).toBe(false)
  }

  await Promise.all(actors.flatMap((a) => [a.teacherContext.close(), a.studentContext.close()]))
})

