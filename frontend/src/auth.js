// auth.js — localStorage 身份信息管理

const KEY = 'selfup_auth'

export const getAuth = () => {
  try { return JSON.parse(localStorage.getItem(KEY) || 'null') } catch { return null }
}

// data: { token, cultivator_id, username, system_name }
export const setAuth = (data) => localStorage.setItem(KEY, JSON.stringify(data))

export const clearAuth = () => localStorage.removeItem(KEY)
