import { useCallback, useEffect, useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import {
  getCultivator, getTechniques, createTechnique, evaluateTechnique,
  cultivate, getMessages, markMessageRead, getCultivatorSects,
  updateTechnique, deleteTechnique, clearInactiveTechniques,
  deleteMessage, clearMessages,
} from '../api'
import { getAuth, clearAuth } from '../auth'
import { useTheme } from '../ThemeContext'

// ── 工具 ────────────────────────────────────────────────────────
function fmtTime(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  const h = String(d.getHours()).padStart(2, '0')
  const m = String(d.getMinutes()).padStart(2, '0')
  return `${h}:${m}`
}

function fmtDateTime(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  const y = d.getFullYear()
  const mo = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  const h = String(d.getHours()).padStart(2, '0')
  const mi = String(d.getMinutes()).padStart(2, '0')
  return `${y}-${mo}-${day} ${h}:${mi}`
}

// 根据当前境界计算每日灵气上限（LORE.md §3.2.1）
function getDailyCap(currentRealm) {
  if (!currentRealm) return 150
  if (currentRealm.startsWith('练气期')) return 150
  if (currentRealm.startsWith('筑基期')) return 200
  if (currentRealm.startsWith('金丹期')) return 280
  if (currentRealm.startsWith('元婴期')) return 350
  return 450
}

// ── 打卡成功提示 ────────────────────────────────────────────────
function Toast({ toast, onDone }) {
  useEffect(() => {
    if (!toast) return
    const t = setTimeout(onDone, 5000)
    return () => clearTimeout(t)
  }, [toast, onDone])

  if (!toast) return null
  return (
    <div className={`toast${toast.breakthrough ? ' breakthrough' : ''}`}>
      {toast.overflow_settled > 0 && (
        <div className="toast-overflow-settled">气海回流 +{toast.overflow_settled} 灵气</div>
      )}
      <div>{toast.message}</div>
      {toast.overflow_added > 0 && (
        <div className="toast-overflow-note">今日灵气已达天道上限，多余 {toast.overflow_added} 灵气流入气海</div>
      )}
    </div>
  )
}

// ── 打卡弹窗 ────────────────────────────────────────────────────
function CheckinModal({ tech, onCancel, onSuccess }) {
  const [note, setNote] = useState('')
  const [photo, setPhoto] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const auth = getAuth()

  async function handleSubmit(e) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const result = await cultivate(auth.cultivator_id, tech.id, note, photo)
      onSuccess(result)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="modal-overlay" onClick={e => e.target === e.currentTarget && onCancel()}>
      <div className="modal">
        <div>
          <div className="modal-title">修炼打卡 · {tech.name}</div>
          <div className="modal-sub">{tech.real_task}</div>
        </div>

        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div className="field">
            <label>修炼感悟（可选）</label>
            <textarea
              className="input"
              placeholder="记录今日所思所感..."
              value={note}
              onChange={e => setNote(e.target.value)}
            />
          </div>

          <div className="field">
            <label>修炼凭证（可选）</label>
            <input
              type="file"
              accept="image/*"
              onChange={e => setPhoto(e.target.files[0] || null)}
              style={{ color: 'var(--text-dim)', fontSize: 12 }}
            />
          </div>

          {error && <div className="login-error">{error}</div>}

          <div className="modal-actions">
            <button type="button" className="btn btn-ghost" onClick={onCancel}>取消</button>
            <button type="submit" className="btn btn-primary" disabled={loading}>
              {loading ? '提交中...' : '完成修炼'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

// ── 添加功法表单（两步流程：填写信息 → 天道定价确认） ──────────────
function AddTechniqueForm({ cultivatorId, onCreated, onCancel }) {
  const [step, setStep] = useState(1)
  const [name, setName] = useState('')
  const [realTask, setRealTask] = useState('')
  const [scheduledTime, setScheduledTime] = useState('')
  const [evaluating, setEvaluating] = useState(false)
  const [evalResult, setEvalResult] = useState(null)
  const [reward, setReward] = useState(50)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  async function handleEvaluate(e) {
    e.preventDefault()
    setError('')
    setEvaluating(true)
    try {
      const result = await evaluateTechnique({ name: name.trim(), real_task: realTask.trim() })
      setEvalResult(result)
      setReward(result.suggested_reward)
      setStep(2)
    } catch (err) {
      setError(err.message)
    } finally {
      setEvaluating(false)
    }
  }

  async function handleSubmit(e) {
    e.preventDefault()
    setError('')
    setSubmitting(true)
    try {
      const tech = await createTechnique({
        cultivator_id: cultivatorId,
        name: name.trim(),
        real_task: realTask.trim(),
        scheduled_time: scheduledTime || null,
        spiritual_energy_reward: reward,
        spiritual_energy_ai_suggested: evalResult.suggested_reward,
        spiritual_energy_min_allowed: evalResult.min_allowed,
        spiritual_energy_max_allowed: evalResult.max_allowed,
      })
      onCreated(tech)
    } catch (err) {
      setError(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  // ── 第二步：确认天道定价 ──────────────────────────────────────
  if (step === 2 && evalResult) {
    return (
      <form className="add-tech-form" onSubmit={handleSubmit}>
        <div className="pricing-header">
          <span className="pricing-title">天道定价确认</span>
          <span className="pricing-tech-name">{name}</span>
        </div>

        <div className="ai-reasoning">{evalResult.reasoning}</div>

        <div className="pricing-verdict">
          天道裁定：{evalResult.min_allowed} ~ {evalResult.max_allowed} 灵气，当前定价：
          <span className="pricing-value">{reward}</span>
        </div>

        <div className="pricing-row">
          <span className="pricing-label">{evalResult.min_allowed}</span>
          <input
            type="range"
            className="pricing-range"
            min={evalResult.min_allowed}
            max={evalResult.max_allowed}
            value={reward}
            onChange={e => setReward(Number(e.target.value))}
          />
          <span className="pricing-label">{evalResult.max_allowed}</span>
          <input
            type="number"
            className="input pricing-number"
            min={evalResult.min_allowed}
            max={evalResult.max_allowed}
            value={reward}
            onChange={e => setReward(
              Math.min(evalResult.max_allowed, Math.max(evalResult.min_allowed, Number(e.target.value) || evalResult.min_allowed))
            )}
          />
          <span className="pricing-unit">灵气</span>
        </div>

        {error && <div className="login-error">{error}</div>}

        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => { setStep(1); setError('') }}>
            返回修改
          </button>
          <button type="button" className="btn btn-ghost btn-sm" onClick={onCancel}>取消</button>
          <button type="submit" className="btn btn-primary btn-sm" disabled={submitting}>
            {submitting ? '创建中...' : '确认创建'}
          </button>
        </div>
      </form>
    )
  }

  // ── 第一步：填写功法信息 ──────────────────────────────────────
  return (
    <form className="add-tech-form" onSubmit={handleEvaluate}>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
        <div className="field">
          <label>功法名称</label>
          <input className="input" placeholder="如：淬体功" value={name} onChange={e => setName(e.target.value)} required />
        </div>
        <div className="field">
          <label>定时督促（可选）</label>
          <input className="input" type="time" value={scheduledTime} onChange={e => setScheduledTime(e.target.value)} />
        </div>
      </div>
      <div className="field">
        <label>现实任务</label>
        <input className="input" placeholder="如：每天健身30分钟" value={realTask} onChange={e => setRealTask(e.target.value)} required />
      </div>
      {error && <div className="login-error">{error}</div>}
      <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
        <button type="button" className="btn btn-ghost btn-sm" onClick={onCancel}>取消</button>
        <button type="submit" className="btn btn-primary btn-sm" disabled={evaluating}>
          {evaluating ? '天道推演中...' : '请天道定价 →'}
        </button>
      </div>
    </form>
  )
}

// ── 编辑功法表单 ─────────────────────────────────────────────────
function EditTechniqueForm({ tech, cultivatorId, onSaved, onCancel }) {
  const isSectTech = !!tech.added_by_sect_id

  const [name, setName] = useState(tech.name)
  const [realTask, setRealTask] = useState(tech.real_task)
  const [scheduledTime, setScheduledTime] = useState(tech.scheduled_time || '')
  const [reprice, setReprice] = useState(false)

  // 重新定价子流程（复用 AddTechniqueForm 的 step2 逻辑）
  const [evalResult, setEvalResult] = useState(null)
  const [reward, setReward] = useState(tech.spiritual_energy_reward)
  const [evaluating, setEvaluating] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  async function handleEvaluate() {
    setEvaluating(true)
    setError('')
    try {
      const result = await evaluateTechnique({ name: name.trim(), real_task: realTask.trim() })
      setEvalResult(result)
      setReward(result.suggested_reward)
      setReprice(true)
    } catch (err) {
      setError(err.message)
    } finally {
      setEvaluating(false)
    }
  }

  async function handleSave(e) {
    e.preventDefault()
    setSubmitting(true)
    setError('')
    try {
      const body = {
        name: name.trim(),
        real_task: realTask.trim(),
        scheduled_time: scheduledTime || null,
      }
      if (evalResult) {
        body.spiritual_energy_reward = reward
        body.spiritual_energy_ai_suggested = evalResult.suggested_reward
        body.spiritual_energy_min_allowed = evalResult.min_allowed
        body.spiritual_energy_max_allowed = evalResult.max_allowed
      }
      const updated = await updateTechnique(tech.id, cultivatorId, body)
      onSaved(updated)
    } catch (err) {
      setError(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form className="add-tech-form" onSubmit={handleSave}>
      <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 8, color: 'var(--cyan)' }}>
        编辑功法
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
        <div className="field">
          <label>功法名称</label>
          <input className="input" value={name} onChange={e => setName(e.target.value)} required />
        </div>
        <div className="field">
          <label>定时督促（可选）</label>
          <input className="input" type="time" value={scheduledTime} onChange={e => setScheduledTime(e.target.value)} />
        </div>
      </div>
      <div className="field">
        <label>现实任务</label>
        <input className="input" value={realTask} onChange={e => setRealTask(e.target.value)} required />
      </div>

      {/* 灵气值修改区 */}
      {!isSectTech && !reprice && (
        <div className="field">
          <label>
            灵气奖励 <span style={{ color: 'var(--text-muted)', fontWeight: 400 }}>（当前：{tech.spiritual_energy_reward}）</span>
          </label>
          <button type="button" className="btn btn-ghost btn-sm" onClick={handleEvaluate} disabled={evaluating}>
            {evaluating ? '天道推演中...' : '重新请天道定价 →'}
          </button>
        </div>
      )}
      {isSectTech && (
        <div style={{ fontSize: 12, color: 'var(--text-muted)', padding: '4px 0' }}>
          宗门功法灵气值不可修改
        </div>
      )}

      {/* 重新定价确认区 */}
      {reprice && evalResult && (
        <div className="pricing-header" style={{ flexDirection: 'column', gap: 8 }}>
          <div className="ai-reasoning">{evalResult.reasoning}</div>
          <div className="pricing-verdict">
            天道裁定：{evalResult.min_allowed} ~ {evalResult.max_allowed}，当前定价：
            <span className="pricing-value">{reward}</span>
          </div>
          <div className="pricing-row">
            <span className="pricing-label">{evalResult.min_allowed}</span>
            <input type="range" className="pricing-range"
              min={evalResult.min_allowed} max={evalResult.max_allowed} value={reward}
              onChange={e => setReward(Number(e.target.value))} />
            <span className="pricing-label">{evalResult.max_allowed}</span>
            <input type="number" className="input pricing-number"
              min={evalResult.min_allowed} max={evalResult.max_allowed} value={reward}
              onChange={e => setReward(Math.min(evalResult.max_allowed, Math.max(evalResult.min_allowed, Number(e.target.value) || evalResult.min_allowed)))} />
            <span className="pricing-unit">灵气</span>
          </div>
        </div>
      )}

      {error && <div className="login-error">{error}</div>}
      <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
        <button type="button" className="btn btn-ghost btn-sm" onClick={onCancel}>取消</button>
        <button type="submit" className="btn btn-primary btn-sm" disabled={submitting}>
          {submitting ? '保存中...' : '保存修改'}
        </button>
      </div>
    </form>
  )
}

// ── 主页面 ──────────────────────────────────────────────────────
export default function Dashboard() {
  const navigate = useNavigate()
  const auth = getAuth()
  const { theme, toggleTheme } = useTheme()

  const [cultivator, setCultivator] = useState(null)
  const [techniques, setTechniques] = useState([])
  const [messages, setMessages] = useState([])
  const [unreadCount, setUnreadCount] = useState(0)
  const [checkinTech, setCheckinTech] = useState(null)
  const [toast, setToast] = useState(null)
  const [addOpen, setAddOpen] = useState(false)
  const [editTech, setEditTech] = useState(null)
  const [deleteTech, setDeleteTech] = useState(null)
  const [deleteLoading, setDeleteLoading] = useState(false)
  const [inactiveTechs, setInactiveTechs] = useState([])
  const [showInactive, setShowInactive] = useState(false)
  const [clearConfirm, setClearConfirm] = useState(false)
  const [clearLoading, setClearLoading] = useState(false)
  const [loading, setLoading] = useState(true)
  const [sectMemberships, setSectMemberships] = useState({ formal: null, visiting: [] })

  const refreshAll = useCallback(async () => {
    try {
      const [cult, techs, allTechs, msgs] = await Promise.all([
        getCultivator(auth.cultivator_id),
        getTechniques(auth.cultivator_id),
        getTechniques(auth.cultivator_id, true),
        getMessages(auth.cultivator_id, false),
      ])
      setCultivator(cult)
      setTechniques(techs)
      setInactiveTechs(allTechs.filter(t => !t.is_active))
      setMessages(msgs.messages)
      setUnreadCount(msgs.messages.filter(m => !m.is_read).length)
    } catch (err) {
      if (err.message.includes('401')) logout()
    }
    // 门派信息（独立加载，失败不影响主界面）
    getCultivatorSects(auth.cultivator_id)
      .then(d => setSectMemberships({ formal: d.formal || null, visiting: d.visiting || [] }))
      .catch(() => {})
  }, [auth?.cultivator_id])

  useEffect(() => {
    refreshAll().finally(() => setLoading(false))
  }, [refreshAll])

  function logout() {
    clearAuth()
    navigate('/login', { replace: true })
  }

  function handleCheckinSuccess(result) {
    setCheckinTech(null)
    const isBreakthrough = result.breakthrough
    let message = isBreakthrough
      ? `恭喜宿主突破至「${result.new_realm}」境界！`
      : `获得 ${result.spiritual_energy_gained} 灵气 · 当前境界 ${result.new_realm}`
    if (result.penalty_energy > 0) {
      message += ` · ${result.penalty_status}，扣除 ${result.penalty_energy} 灵气`
    }
    setToast({
      breakthrough: isBreakthrough,
      message,
      overflow_added: result.overflow_added || 0,
      overflow_settled: result.overflow_settled || 0,
    })
    refreshAll()
  }

  async function handleDeleteConfirm() {
    if (!deleteTech) return
    setDeleteLoading(true)
    try {
      await deleteTechnique(deleteTech.id, auth.cultivator_id)
      setDeleteTech(null)
      await refreshAll()
    } catch (err) {
      setDeleteTech(null)
    } finally {
      setDeleteLoading(false)
    }
  }

  async function handleRestoreTech(tech) {
    try {
      await updateTechnique(tech.id, auth.cultivator_id, { is_active: true })
      await refreshAll()
    } catch {}
  }

  async function handleClearInactive() {
    setClearLoading(true)
    try {
      await clearInactiveTechniques(auth.cultivator_id)
      setClearConfirm(false)
      await refreshAll()
    } catch {}
    finally {
      setClearLoading(false)
    }
  }

  async function handleDeleteMsg(id) {
    try {
      await deleteMessage(id, auth.cultivator_id)
      setMessages(prev => prev.filter(m => m.id !== id))
      setUnreadCount(prev => {
        const msg = messages.find(m => m.id === id)
        return msg && !msg.is_read ? prev - 1 : prev
      })
    } catch {}
  }

  async function handleClearMsgs() {
    try {
      await clearMessages(auth.cultivator_id)
      setMessages([])
      setUnreadCount(0)
    } catch {}
  }

  async function handleMarkRead(msg) {
    if (msg.is_read) return
    await markMessageRead(msg.id).catch(() => {})
    setMessages(prev => prev.map(m => m.id === msg.id ? { ...m, is_read: true } : m))
    setUnreadCount(prev => Math.max(0, prev - 1))
  }

  if (loading) {
    return <div className="loading-center">正在加载修炼数据...</div>
  }

  const progressPct = cultivator ? Math.round(cultivator.progress_to_next * 100) : 0

  return (
    <div className="dashboard">
      {/* ── 顶部状态栏 ────────────────────── */}
      <header className="dash-header">
        <span className="dash-logo">Self-UP</span>
        <span style={{ color: 'var(--text-dim)', fontSize: 13 }}>{auth.username}</span>
        {cultivator && <span className="realm-badge">{cultivator.current_realm}</span>}
        {cultivator && (
          <span className="streak-badge">
            {cultivator.current_streak > 0 ? `连续${cultivator.current_streak}天` : '今日未修炼'}
          </span>
        )}
        <div className="dash-header-spacer" />
        <button
          className="msg-btn"
          onClick={() => document.querySelector('.messages-sidebar')?.scrollIntoView()}
        >
          系统消息
          {unreadCount > 0 && <span className="msg-badge">{unreadCount}</span>}
        </button>
        <button className="btn btn-ghost btn-sm" onClick={toggleTheme}>
          {theme === 'dark' ? '亮色' : '暗色'}
        </button>
        <Link to="/history" className="btn btn-ghost btn-sm">修炼历史</Link>
        <Link to="/dialogue" className="btn btn-ghost btn-sm">与系统对话</Link>
        <button className="btn btn-ghost btn-sm btn-danger" onClick={logout}>退出</button>
      </header>

      {/* ── 灵气进度条 ────────────────────── */}
      {cultivator && (
        <div className="energy-bar-wrap">
          <div className="energy-labels">
            <span className="realm-name">{cultivator.current_realm}</span>
            <span>
              {cultivator.progress_to_next < 1
                ? `灵气 ${cultivator.total_spiritual_energy.toLocaleString()} · 距下一阶 ${progressPct}%`
                : `灵气 ${cultivator.total_spiritual_energy.toLocaleString()} · 已至圆满`}
            </span>
            <span className="daily-cap-info">
              今日：{cultivator.daily_spiritual_energy_earned} / {getDailyCap(cultivator.current_realm)}
            </span>
          </div>
          <div className="energy-bar-track">
            <div className="energy-bar-fill" style={{ width: `${progressPct}%` }} />
          </div>
          {cultivator.spiritual_energy_overflow > 0 && (
            <div className="overflow-status">
              气海：{cultivator.spiritual_energy_overflow} 灵气蓄积中，明日回流{' '}
              {Math.floor(cultivator.spiritual_energy_overflow * 0.3)} 灵气
            </div>
          )}
        </div>
      )}

      {/* ── 门派信息栏 ────────────────────── */}
      <div className="sect-panel">
        {sectMemberships.formal ? (
          <>
            <span className="sect-panel-icon">⛩</span>
            <span className="sect-panel-name">{sectMemberships.formal.name}</span>
            <span className="sect-panel-formal-badge">正式弟子</span>
            {messages.some(m => !m.is_read && m.message.startsWith('【')) && (
              <span className="sect-panel-badge">有新推送</span>
            )}
            {sectMemberships.visiting.length > 0 && (
              <span className="sect-panel-visiting-summary">
                游历 {sectMemberships.visiting.length} 宗：{sectMemberships.visiting.map(v => v.name).join('、')}
              </span>
            )}
            <div className="sect-panel-spacer" />
            <Link to={`/sects/quests?sect_id=${sectMemberships.formal.sect_id}`} className="sect-panel-link" style={{ marginRight: 4 }}>宗门任务</Link>
            <Link to="/sects/resources" className="sect-panel-link">秘籍 →</Link>
            <Link to="/sects" className="btn btn-ghost btn-sm" style={{ fontSize: 11, padding: '3px 10px' }}>
              门派大厅
            </Link>
          </>
        ) : sectMemberships.visiting.length > 0 ? (
          <>
            <span className="sect-panel-icon">⛩</span>
            <span className="sect-panel-name" style={{ color: 'var(--text-dim)' }}>游历中</span>
            <span className="sect-panel-visiting-summary">
              {sectMemberships.visiting.map(v => v.name).join('、')}
            </span>
            <div className="sect-panel-spacer" />
            <Link to="/sects" className="btn btn-ghost btn-sm" style={{ fontSize: 11, padding: '3px 10px' }}>
              门派大厅
            </Link>
          </>
        ) : (
          <Link to="/sects" className="sect-panel-empty">
            尚未拜入宗门，前往门派大厅 →
          </Link>
        )}
      </div>

      {/* ── 主内容 ────────────────────────── */}
      <div className="dash-body">
        {/* 功法列表 */}
        <div className="techniques-panel">
          <div className="panel-title">修炼功法</div>

          {techniques.length === 0 && !addOpen && (
            <div style={{ color: 'var(--text-muted)', fontSize: 13, marginBottom: 14 }}>
              尚无功法，请先添加
            </div>
          )}

          {techniques.map(tech => (
            editTech?.id === tech.id ? (
              <EditTechniqueForm
                key={tech.id}
                tech={tech}
                cultivatorId={auth.cultivator_id}
                onSaved={updated => {
                  setTechniques(prev => prev.map(t => t.id === updated.id ? updated : t))
                  setEditTech(null)
                }}
                onCancel={() => setEditTech(null)}
              />
            ) : (
              <div key={tech.id} className={`technique-card${tech.completed_today ? ' done' : ''}`}>
                <div className="tech-info">
                  <div className="tech-name">
                    {tech.name}
                    {tech.added_by_sect_id && <span className="tech-sect-badge">宗门</span>}
                  </div>
                  <div className="tech-task">{tech.real_task}</div>
                  <div className="tech-meta">
                    {tech.scheduled_time && <span className="tech-time">⏰ {tech.scheduled_time}</span>}
                    <span className="tech-energy">✦ {tech.spiritual_energy_reward} 灵气</span>
                  </div>
                </div>
                <div className="tech-action-group">
                  {tech.completed_today
                    ? <span className="tech-done-badge">今日已修炼 ✓</span>
                    : (
                      <button className="btn btn-primary btn-sm" onClick={() => setCheckinTech(tech)}>
                        开始修炼
                      </button>
                    )
                  }
                  <div className="tech-icon-btns">
                    <button
                      className="btn-icon"
                      onClick={() => setEditTech(tech)}
                      title="编辑功法"
                    >✏</button>
                    <button
                      className={`btn-icon${tech.added_by_sect_id ? ' btn-icon-disabled' : ' btn-icon-danger'}`}
                      onClick={() => !tech.added_by_sect_id && setDeleteTech(tech)}
                      title={tech.added_by_sect_id ? '宗门功法随离宗自动移除' : '废弃功法'}
                      disabled={!!tech.added_by_sect_id}
                    >🗑</button>
                  </div>
                </div>
              </div>
            )
          ))}

          {addOpen
            ? (
              <AddTechniqueForm
                cultivatorId={auth.cultivator_id}
                onCreated={tech => { setTechniques(prev => [...prev, tech]); setAddOpen(false) }}
                onCancel={() => setAddOpen(false)}
              />
            )
            : (
              <button className="add-tech-btn" onClick={() => setAddOpen(true)}>
                <span style={{ fontSize: 18, lineHeight: 1 }}>+</span> 添加功法
              </button>
            )
          }

          {/* 已废弃功法折叠区 */}
          {inactiveTechs.length > 0 && (
            <div className="inactive-techniques">
              <div className="inactive-toggle-row">
                <button className="inactive-toggle" onClick={() => setShowInactive(v => !v)}>
                  已废弃的功法（{inactiveTechs.length}个）{showInactive ? ' ▲' : ' ▼'}
                </button>
                <button
                  className="btn btn-danger btn-xs"
                  onClick={() => setClearConfirm(true)}
                  title="永久删除所有已废弃功法"
                >
                  清空
                </button>
              </div>
              {showInactive && inactiveTechs.map(tech => (
                <div key={tech.id} className="technique-card inactive-card">
                  <div className="tech-info" style={{ opacity: 0.5 }}>
                    <div className="tech-name">{tech.name}</div>
                    <div className="tech-task">{tech.real_task}</div>
                  </div>
                  <button className="btn btn-ghost btn-sm" onClick={() => handleRestoreTech(tech)}>
                    恢复
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* 系统消息侧边栏 */}
        <div className="messages-sidebar">
          <div className="messages-sidebar-header">
            <span>系统消息</span>
            {unreadCount > 0 && <span className="msg-badge">{unreadCount} 未读</span>}
            <div className="msg-header-spacer" />
            {messages.length > 0 && (
              <button
                className="btn-msg-clear"
                onClick={handleClearMsgs}
                title="清空全部消息"
              >
                清空
              </button>
            )}
          </div>

          <div className="messages-list">
            {messages.length === 0
              ? <div className="empty-msg">暂无消息</div>
              : messages.map(msg => (
                <div
                  key={msg.id}
                  className={`msg-item${msg.is_read ? '' : ' unread'}`}
                  onClick={() => handleMarkRead(msg)}
                >
                  <div className="msg-item-text">
                    {!msg.is_read && <span className="msg-item-unread-dot" />}
                    {msg.message}
                  </div>
                  <div className="msg-item-bottom">
                    <span className="msg-item-time">{fmtDateTime(msg.sent_at)}</span>
                    <button
                      className="btn-msg-delete"
                      onClick={e => { e.stopPropagation(); handleDeleteMsg(msg.id) }}
                      title="删除此消息"
                    >
                      ×
                    </button>
                  </div>
                </div>
              ))
            }
          </div>

          <div className="messages-footer">
            <Link to="/dialogue" className="btn btn-ghost btn-sm btn-full">
              与随身系统对话 →
            </Link>
          </div>
        </div>
      </div>

      {/* 废弃功法确认弹窗 */}
      {deleteTech && (
        <div className="modal-overlay" onClick={e => e.target === e.currentTarget && setDeleteTech(null)}>
          <div className="modal">
            <div className="modal-title">废弃功法 · {deleteTech.name}</div>
            <div style={{ fontSize: 13, color: 'var(--text-dim)', lineHeight: 1.8 }}>
              废弃此功法后，历史修炼记录将保留，但此功法不再出现在每日功课中。确认废弃？
            </div>
            <div className="modal-actions">
              <button className="btn btn-ghost" onClick={() => setDeleteTech(null)} disabled={deleteLoading}>
                再想想
              </button>
              <button className="btn btn-danger" onClick={handleDeleteConfirm} disabled={deleteLoading}>
                {deleteLoading ? '处理中...' : '确认废弃'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 清空废弃功法确认弹窗 */}
      {clearConfirm && (
        <div className="modal-overlay" onClick={e => e.target === e.currentTarget && setClearConfirm(false)}>
          <div className="modal">
            <div className="modal-title">清空废弃功法</div>
            <div style={{ fontSize: 13, color: 'var(--text-dim)', lineHeight: 1.8 }}>
              将永久删除全部 <strong style={{ color: 'var(--danger)' }}>{inactiveTechs.length} 个</strong>已废弃功法及其历史修炼记录，且<strong style={{ color: 'var(--danger)' }}>不可恢复</strong>。
              <br />
              正式宗门自动添加的功法不受影响（需离宗移除）。
            </div>
            <div className="modal-actions">
              <button className="btn btn-ghost" onClick={() => setClearConfirm(false)} disabled={clearLoading}>
                再想想
              </button>
              <button className="btn btn-danger" onClick={handleClearInactive} disabled={clearLoading}>
                {clearLoading ? '清空中...' : '确认清空'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 打卡弹窗 */}
      {checkinTech && (
        <CheckinModal
          tech={checkinTech}
          onCancel={() => setCheckinTech(null)}
          onSuccess={handleCheckinSuccess}
        />
      )}

      {/* 提示 Toast */}
      <Toast toast={toast} onDone={() => setToast(null)} />
    </div>
  )
}
