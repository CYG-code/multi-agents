import api from './api.js'

export function getExportRooms(params = {}) {
  return api.get('/exports/rooms', { params })
}

export function previewExport(payload) {
  return api.post('/exports/preview', payload)
}

export async function downloadExport(payload) {
  const token = localStorage.getItem('token')
  const response = await fetch('/api/exports/download', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(payload || {}),
  })

  if (!response.ok) {
    let message = `下载失败（${response.status}）`
    try {
      const data = await response.json()
      message = data?.detail?.message || data?.detail || message
    } catch {
      // keep fallback message
    }
    throw new Error(message)
  }

  const blob = await response.blob()
  const disposition = response.headers.get('content-disposition') || ''
  const match = disposition.match(/filename="?([^"]+)"?/)
  const filename = match?.[1] || `experiment_export_${new Date().toISOString().replace(/[:.]/g, '-')}.zip`

  const url = window.URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  window.URL.revokeObjectURL(url)
  return { filename }
}

