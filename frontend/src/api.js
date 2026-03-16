// api.js — 后端请求封装
// Vite proxy 将 /api/* 转发至 http://localhost:8000

function getToken() {
  try {
    const auth = JSON.parse(localStorage.getItem('selfup_auth') || 'null')
    return auth?.token ?? null
  } catch {
    return null
  }
}

async function apiFetch(path, options = {}) {
  const token = getToken()
  const headers = {
    ...(options.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...options.headers,
  }
  const res = await fetch(path, { ...options, headers })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || '请求失败')
  }
  return res.json()
}

// ── 认证 ──────────────────────────────────────────────────────
export const register = (username, email, password) =>
  apiFetch('/api/auth/register', {
    method: 'POST',
    body: JSON.stringify({ username, email, password }),
  })

export const login = (username, password) =>
  apiFetch('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  })

// ── 修士信息 ──────────────────────────────────────────────────
export const getCultivator = (id) => apiFetch(`/api/cultivators/${id}`)

// ── 功法 ──────────────────────────────────────────────────────
export const getTechniques = (cultivatorId, includeInactive = false) =>
  apiFetch(`/api/techniques?cultivator_id=${cultivatorId}&include_inactive=${includeInactive}`)

export const createTechnique = (data) =>
  apiFetch('/api/techniques', { method: 'POST', body: JSON.stringify(data) })

export const evaluateTechnique = (data) =>
  apiFetch('/api/techniques/evaluate', { method: 'POST', body: JSON.stringify(data) })

export const updateTechnique = (techniqueId, cultivatorId, data) =>
  apiFetch(`/api/techniques/${techniqueId}?cultivator_id=${cultivatorId}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  })

export const deleteTechnique = (techniqueId, cultivatorId) =>
  apiFetch(`/api/techniques/${techniqueId}?cultivator_id=${cultivatorId}`, {
    method: 'DELETE',
  })

export const clearInactiveTechniques = (cultivatorId) =>
  apiFetch(`/api/techniques/inactive?cultivator_id=${cultivatorId}`, {
    method: 'DELETE',
  })

// ── 打卡修炼 ──────────────────────────────────────────────────
export const cultivate = (cultivatorId, techniqueId, note, photoFile) => {
  const form = new FormData()
  form.append('cultivator_id', cultivatorId)
  form.append('technique_id', techniqueId)
  if (note) form.append('note', note)
  if (photoFile) form.append('photo', photoFile)
  return apiFetch('/api/cultivate', { method: 'POST', body: form })
}

// ── 系统消息 ──────────────────────────────────────────────────
export const getMessages = (cultivatorId, unreadOnly = true) =>
  apiFetch(`/api/system/messages?cultivator_id=${cultivatorId}&unread_only=${unreadOnly}`)

export const markMessageRead = (messageId) =>
  apiFetch(`/api/system/messages/${messageId}/read`, { method: 'PATCH' })

export const deleteMessage = (messageId, cultivatorId) =>
  apiFetch(`/api/system/messages/${messageId}?cultivator_id=${cultivatorId}`, { method: 'DELETE' })

export const clearMessages = (cultivatorId) =>
  apiFetch(`/api/system/messages?cultivator_id=${cultivatorId}`, { method: 'DELETE' })

// ── 对话 ──────────────────────────────────────────────────────
export const sendDialogue = (cultivatorId, message) =>
  apiFetch('/api/system/dialogue', {
    method: 'POST',
    body: JSON.stringify({ cultivator_id: cultivatorId, message }),
  })

// ── 门派 ──────────────────────────────────────────────────────
export const getSects = (cultivatorId) =>
  apiFetch(`/api/sects${cultivatorId != null ? `?cultivator_id=${cultivatorId}` : ''}`)

export const getCultivatorSects = (cultivatorId) =>
  apiFetch(`/api/sects/memberships?cultivator_id=${cultivatorId}`)

export const joinSect = (cultivatorId, sectId, membershipType = 'formal') =>
  apiFetch('/api/sects/join', {
    method: 'POST',
    body: JSON.stringify({ cultivator_id: cultivatorId, sect_id: sectId, membership_type: membershipType }),
  })

export const leaveSect = (cultivatorId, sectId) =>
  apiFetch('/api/sects/leave', {
    method: 'POST',
    body: JSON.stringify({ cultivator_id: cultivatorId, sect_id: sectId }),
  })

export const getSectResources = (cultivatorId, sectId = null) =>
  apiFetch(`/api/sects/resources?cultivator_id=${cultivatorId}${sectId ? `&sect_id=${sectId}` : ''}`)

export const getSectQuests = (sectId, cultivatorId) =>
  apiFetch(`/api/sects/${sectId}/quests?cultivator_id=${cultivatorId}`)

export const getSectTechniques = (sectId, cultivatorId) =>
  apiFetch(`/api/sects/${sectId}/techniques?cultivator_id=${cultivatorId}`)

export const addSectTechnique = (sectId, cultivatorId, techniqueName) =>
  apiFetch(`/api/sects/${sectId}/techniques/add`, {
    method: 'POST',
    body: JSON.stringify({ cultivator_id: cultivatorId, technique_name: techniqueName }),
  })

// ── 修炼历史 ──────────────────────────────────────────────────
export const getCultivationHistory = (cultivatorId, page = 1, pageSize = 20) =>
  apiFetch(`/api/cultivation/history?cultivator_id=${cultivatorId}&page=${page}&page_size=${pageSize}`)
