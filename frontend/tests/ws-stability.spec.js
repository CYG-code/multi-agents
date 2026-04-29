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

async function tryLoginWithTeacher(apiBase, request) {
  const account = TEST_ACCOUNTS.teacher
  const attempts = []
  console.log(`[WS-E2E] Using test account: teacher / ${account.username}`)

  try {
    const resp = await request.post(`${apiBase}/auth/login`, {
      data: { username: account.username, password: account.password },
    })
    const body = await resp.json().catch(() => ({}))
    attempts.push({ accountType: 'teacher', username: account.username, status: resp.status(), ok: resp.ok() })
    if (resp.ok() && body?.access_token && body?.user) {
      return {
        ok: true,
        token: body.access_token,
        user: body.user,
        attempts,
      }
    }
  } catch (error) {
    attempts.push({ accountType: 'teacher', username: account.username, status: 'network-error', error: String(error) })
  }

  return { ok: false, attempts }
}

async function createRoom(apiBase, request, token) {
  const roomName = `WS-Stability-${Date.now()}`
  const resp = await request.post(`${apiBase}/rooms`, {
    headers: {
      Authorization: `Bearer ${token}`,
    },
    data: {
      name: roomName,
    },
  })
  const body = await resp.json().catch(() => ({}))
  return { ok: resp.ok(), status: resp.status(), body }
}

async function joinRoom(apiBase, request, token, roomId) {
  const url = `${apiBase}/rooms/${roomId}/join`
  const resp = await request.post(url, {
    headers: {
      Authorization: `Bearer ${token}`,
    },
  })
  const body = await resp.json().catch(() => ({}))
  return { ok: resp.ok(), status: resp.status(), body, url }
}

test('websocket stability in room page (30s)', async ({ page, baseURL, request }) => {
  const targetBase = baseURL || process.env.BASE_URL || 'http://localhost:5173'
  const apiBase = `${targetBase.replace(/\/$/, '')}/api`

  let roomId = process.env.TEST_ROOM_ID || null
  let loginResult = null
  let createRoomResult = null
  let joinRoomResult = null
  let isRoomMemberPrepared = false
  const wsCloseDetailsFromPage = []
  const observedApiResponses = []

  if (!roomId) {
    loginResult = await tryLoginWithTeacher(apiBase, request)

    if (!loginResult.ok) {
      throw new Error(
        [
          'Auto room resolution failed: cannot login to create room.',
          'Tried /api/auth/login with teacher test account and failed.',
          `Attempts: ${JSON.stringify(loginResult.attempts)}`,
          'Please configure TEST_TEACHER_USERNAME / TEST_TEACHER_PASSWORD, or fallback TEST_USERNAME / TEST_PASSWORD.',
        ].join(' ')
      )
    }

    const created = await createRoom(apiBase, request, loginResult.token)
    createRoomResult = created
    if (!created.ok || !created.body?.id) {
      throw new Error(
        [
          'Auto room creation failed via POST /api/rooms.',
          `status=${created.status}`,
          `body=${JSON.stringify(created.body)}`,
          'Likely missing teacher permission or backend route mismatch.',
        ].join(' ')
      )
    }

    roomId = String(created.body.id)
    const joined = await joinRoom(apiBase, request, loginResult.token, roomId)
    joinRoomResult = joined
    if (joined.status === 200) {
      isRoomMemberPrepared = true
    } else if (joined.status === 409 || String(joined.body?.detail || '').includes('已加入')) {
      isRoomMemberPrepared = true
    } else if (joined.status === 403) {
      throw new Error(
        [
          'Teacher account has no permission to join the created room.',
          'Test setup failure (not websocket stability failure).',
          `joinStatus=${joined.status}`,
          `joinUrl=${joined.url}`,
          `joinBody=${JSON.stringify(joined.body)}`,
        ].join(' ')
      )
    } else {
      throw new Error(
        [
          'Join room failed during test setup.',
          `joinStatus=${joined.status}`,
          `joinUrl=${joined.url}`,
          `joinBody=${JSON.stringify(joined.body)}`,
        ].join(' ')
      )
    }
  }

  if (!loginResult) {
    loginResult = await tryLoginWithTeacher(apiBase, request)
  }

  if (!loginResult?.ok) {
    throw new Error(
      [
        'Cannot establish authenticated browser session.',
        'Room id is known, but login failed.',
        `Attempts: ${JSON.stringify(loginResult?.attempts || [])}`,
        'Please configure TEST_TEACHER_USERNAME / TEST_TEACHER_PASSWORD, or fallback TEST_USERNAME / TEST_PASSWORD.',
      ].join(' ')
    )
  }

  page.on('console', (msg) => {
    const t = msg.type()
    const txt = msg.text()
    const hitKeyword = /(WS-Debug|WebSocket|auth|token|router)/i.test(txt)
    if (t === 'error' || t === 'warning' || hitKeyword) {
      console.log(`[BrowserConsole][${t}] ${txt}`)
    }
  })

  page.on('pageerror', (error) => {
    console.log('[PageError]', String(error))
  })

  page.on('response', (resp) => {
    const url = resp.url()
    const status = resp.status()
    const hit =
      url.includes('/api/auth/login') ||
      url.includes('/api/rooms') ||
      (roomId && url.includes(`/api/rooms/${roomId}`))
    if (hit) {
      observedApiResponses.push({ status, url })
      console.log('[HTTP]', status, url)
    }
  })

  await page.exposeFunction('__pwWsCloseReport', (detail) => {
    wsCloseDetailsFromPage.push(detail)
  })

  await page.addInitScript(
    ({ token, user }) => {
      const NativeWebSocket = window.WebSocket
      const wsDiag = []
      function WrappedWebSocket(...args) {
        const ws = new NativeWebSocket(...args)
        const rec = {
          url: String(args[0] || ''),
          createdAt: Date.now(),
          closedAt: null,
          closeCode: null,
          closeReason: null,
          lifetimeMs: null,
        }
        wsDiag.push(rec)
        ws.addEventListener('close', (event) => {
          rec.closedAt = Date.now()
          rec.closeCode = event?.code ?? null
          rec.closeReason = event?.reason ?? ''
          rec.lifetimeMs = rec.closedAt - rec.createdAt
          try {
            if (typeof window.__pwWsCloseReport === 'function') {
              window.__pwWsCloseReport({ ...rec })
            }
          } catch {
            // ignore report errors
          }
        })
        return ws
      }
      WrappedWebSocket.prototype = NativeWebSocket.prototype
      Object.setPrototypeOf(WrappedWebSocket, NativeWebSocket)
      window.WebSocket = WrappedWebSocket
      window.__wsDiag = wsDiag
      window.localStorage.setItem('token', token)
      window.localStorage.setItem('user', JSON.stringify(user))
    },
    { token: loginResult.token, user: loginResult.user }
  )
  console.log('[WS-E2E] localStorage prewrite prepared', {
    tokenPrepared: Boolean(loginResult.token),
    userPrepared: Boolean(loginResult.user),
  })

  const targetPath = `/room/${roomId}`
  const targetUrl = `${targetBase}${targetPath}`
  const events = []

  page.on('websocket', (ws) => {
    const createdAt = Date.now()
    const url = ws.url()
    const item = {
      url,
      createdAt,
      closedAt: null,
      closeEvents: 0,
    }
    events.push(item)

    ws.on('close', () => {
      item.closedAt = Date.now()
      item.closeEvents += 1
    })
  })

  const response = await page.goto(targetUrl, { waitUntil: 'domcontentloaded' })
  expect(response, 'page response should exist').toBeTruthy()
  const afterGoto = await page.evaluate(() => {
    const token = window.localStorage.getItem('token')
    const user = window.localStorage.getItem('user')
    const href = window.location.href
    return {
      hasToken: Boolean(token),
      hasUser: Boolean(user),
      href,
      redirectedToLogin: /\/login(?:\?|$|#)/.test(href),
    }
  })
  console.log('[WS-E2E] post-goto auth check', afterGoto)
  if (afterGoto.redirectedToLogin) {
    throw new Error(
      [
        'Page redirected to /login after goto room page.',
        'Possible auth localStorage write failed or was cleared by app.',
        `href=${afterGoto.href}`,
        `hasToken=${afterGoto.hasToken}`,
        `hasUser=${afterGoto.hasUser}`,
      ].join(' ')
    )
  }

  await page.waitForTimeout(30000)

  const roomSockets = events.filter((e) => e.url.includes(`/ws/${roomId}`))

  expect(
    roomSockets.length,
    'No room websocket created. Possible causes: not actually in room page, auth setup failed, or room membership failed.'
  ).toBeGreaterThan(0)

  const createdTimes = roomSockets.map((e) => e.createdAt).sort((a, b) => a - b)
  const tooManyConnections = roomSockets.length > 3
  const periodicReconnect = hasFourSecondPattern(createdTimes)
  const hasLongLived = roomSockets.some((e) => {
    const end = e.closedAt ?? Date.now()
    return end - e.createdAt >= 10000
  })

  console.log('[WS-E2E] summary', {
    targetUrl,
    roomId,
    autoResolvedRoom: !process.env.TEST_ROOM_ID,
    loginAccountType: 'teacher',
    loginUser: loginResult.user?.username,
    createRoomStatus: createRoomResult?.status ?? null,
    joinRoomStatus: joinRoomResult?.status ?? null,
    isRoomMemberPrepared,
    roomSockets: roomSockets.length,
    allSockets: events.length,
    periodicReconnect,
    hasLongLived,
    apiResponses: observedApiResponses,
    details: roomSockets.map((e) => ({
      url: e.url,
      createdAt: e.createdAt,
      closedAt: e.closedAt,
      livedMs: (e.closedAt ?? Date.now()) - e.createdAt,
    })),
    closeDetailsFromPage: wsCloseDetailsFromPage.filter((e) => e.url.includes(`/ws/${roomId}`)),
  })
  const roomCloseDetails = wsCloseDetailsFromPage.filter((e) => e.url.includes(`/ws/${roomId}`))
  const authClose = roomCloseDetails.find((e) => [4001, 4002, 4003].includes(Number(e.closeCode)))
  if (authClose) {
    console.log('[WS-E2E] auth close detected', {
      note: 'This is business auth close, not network jitter.',
      closeCode: authClose.closeCode,
      closeReason: authClose.closeReason,
      lifetimeMs: authClose.lifetimeMs,
    })
  }

  expect(
    tooManyConnections,
    `WebSocket created too many times in 30s (${roomSockets.length}). Details: ${JSON.stringify(roomSockets.map((e) => ({ url: e.url, createdAt: e.createdAt, closedAt: e.closedAt })))}`
  ).toBe(false)

  expect(periodicReconnect, 'Detected roughly 4-second reconnect cycle.').toBe(false)
  expect(hasLongLived, 'No websocket stayed alive for over 10 seconds.').toBe(true)
  expect(roomSockets.length, `Expected room websocket create count <=2, got ${roomSockets.length}`).toBeLessThanOrEqual(2)
})
