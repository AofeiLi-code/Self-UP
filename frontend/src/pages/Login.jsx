import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { login, register } from '../api'
import { setAuth } from '../auth'
import { useTheme } from '../ThemeContext'

export default function Login() {
  const navigate = useNavigate()
  const { theme, toggleTheme } = useTheme()
  const [mode, setMode] = useState('login')      // 'login' | 'register'
  const [username, setUsername] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      let data
      if (mode === 'login') {
        data = await login(username, password)
      } else {
        if (!email) { setError('请填写传音符（邮箱）'); setLoading(false); return }
        data = await register(username, email, password)
      }
      setAuth({ token: data.access_token, cultivator_id: data.cultivator_id, username: data.username, system_name: data.system_name })
      navigate('/dashboard', { replace: true })
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="login-page">
      {/* 主题切换（右上角悬浮） */}
      <button className="btn btn-ghost btn-sm theme-toggle-float" onClick={toggleTheme}>
        {theme === 'dark' ? '亮色' : '暗色'}
      </button>

      <div className="login-card">
        <div className="login-header">
          <div className="login-title">Self-UP · 踏入修仙之路</div>
          <div className="login-sub">把每一次自律当作一次修炼</div>
        </div>

        <form className="login-form" onSubmit={handleSubmit}>
          <div className="field">
            <label>道号（用户名）</label>
            <input
              className="input"
              placeholder="取一个响亮的道号"
              value={username}
              onChange={e => setUsername(e.target.value)}
              required
              autoFocus
            />
          </div>

          {mode === 'register' && (
            <div className="field">
              <label>传音符（邮箱）</label>
              <input
                className="input"
                type="email"
                placeholder="用于接收系统通知"
                value={email}
                onChange={e => setEmail(e.target.value)}
              />
            </div>
          )}

          <div className="field">
            <label>密法印记（密码）</label>
            <input
              className="input"
              type="password"
              placeholder="至少6位"
              value={password}
              onChange={e => setPassword(e.target.value)}
              required
              minLength={6}
            />
          </div>

          {error && <div className="login-error">{error}</div>}

          <button className="btn btn-primary btn-full" type="submit" disabled={loading}>
            {loading ? '正在...' : mode === 'login' ? '踏入修炼界' : '开始修炼之路'}
          </button>
        </form>

        <div className="login-toggle">
          {mode === 'login' ? (
            <>尚未踏入？<button onClick={() => { setMode('register'); setError('') }}>立即注册</button></>
          ) : (
            <>已有道号？<button onClick={() => { setMode('login'); setError('') }}>返回登录</button></>
          )}
        </div>
      </div>
    </div>
  )
}
