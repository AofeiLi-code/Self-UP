import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { addSectTechnique, getSectTechniques, getSects, joinSect, leaveSect } from '../api'
import { getAuth } from '../auth'
import { useTheme } from '../ThemeContext'

const DIFFICULTY_COLOR = {
  '入门': 'var(--success)',
  '中等': 'var(--gold)',
  '高级': 'var(--danger)',
}

export default function Sects() {
  const auth = getAuth()
  const { theme, toggleTheme } = useTheme()

  const [sects, setSects] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  // confirmSect: { sect, joinType } | null
  const [confirmSect, setConfirmSect] = useState(null)
  const [welcomeMsg, setWelcomeMsg] = useState('')
  const [welcomeType, setWelcomeType] = useState('formal')
  const [actionLoading, setActionLoading] = useState(false)
  // sectTechMap: { [sect_str_id]: [{ name, real_task, spiritual_energy_reward, is_added }] }
  const [sectTechMap, setSectTechMap] = useState({})

  const currentFormalSect = sects.find(s => s.membership_type === 'formal') || null
  const visitingSects = sects.filter(s => s.membership_type === 'visiting')

  async function fetchSects() {
    try {
      const data = await getSects(auth.cultivator_id)
      setSects(data.sects)
      // 加载所有已加入宗门的功法列表
      const memberSects = data.sects.filter(s => s.membership_type != null)
      if (memberSects.length > 0) {
        const entries = await Promise.all(
          memberSects.map(async s => {
            try {
              const td = await getSectTechniques(s.sect_id, auth.cultivator_id)
              return [s.sect_id, td.techniques]
            } catch {
              return [s.sect_id, []]
            }
          })
        )
        setSectTechMap(Object.fromEntries(entries))
      }
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchSects() }, [])

  async function handleJoin() {
    if (!confirmSect) return
    setActionLoading(true)
    setError('')
    try {
      const result = await joinSect(auth.cultivator_id, confirmSect.sect.sect_id, confirmSect.joinType)
      setConfirmSect(null)
      setWelcomeMsg(result.welcome_message)
      setWelcomeType(result.membership_type)
      await fetchSects()
    } catch (e) {
      setError(e.message)
      setConfirmSect(null)
    } finally {
      setActionLoading(false)
    }
  }

  async function handleLeave(sectId) {
    setActionLoading(true)
    setError('')
    try {
      await leaveSect(auth.cultivator_id, sectId)
      await fetchSects()
    } catch (e) {
      setError(e.message)
    } finally {
      setActionLoading(false)
    }
  }

  async function handleAddTech(sectStrId, techniqueName) {
    setActionLoading(true)
    setError('')
    try {
      await addSectTechnique(sectStrId, auth.cultivator_id, techniqueName)
      const td = await getSectTechniques(sectStrId, auth.cultivator_id)
      setSectTechMap(prev => ({ ...prev, [sectStrId]: td.techniques }))
    } catch (e) {
      setError(e.message)
    } finally {
      setActionLoading(false)
    }
  }

  if (loading) return <div className="loading-center">正在查询宗门信息...</div>

  return (
    <div className="sect-hall">
      {/* 顶部导航栏 */}
      <header className="dash-header">
        <Link to="/dashboard" className="btn btn-ghost btn-sm">← 返回</Link>
        <span className="dash-logo">门派大厅</span>
        <div className="dash-header-spacer" />
        <button className="btn btn-ghost btn-sm" onClick={toggleTheme}>
          {theme === 'dark' ? '亮色' : '暗色'}
        </button>
      </header>

      {/* 标题区 */}
      <div className="sect-hall-title">
        <div className="sect-hall-h1">宗门列表</div>
        <div className="sect-hall-sub">选择你的修炼之路</div>

        {/* 正式宗门状态栏 */}
        {currentFormalSect && (
          <div className="sect-current-bar">
            <span>正式宗门：<strong>{currentFormalSect.name}</strong></span>
            <div style={{ flex: 1 }} />
            <Link to={`/sects/quests?sect_id=${currentFormalSect.sect_id}`} className="btn btn-ghost btn-sm">宗门任务</Link>
            <Link to={`/sects/resources?sect_id=${currentFormalSect.sect_id}`} className="btn btn-gold btn-sm">宗门秘籍 →</Link>
            <button
              className="btn btn-danger btn-ghost btn-sm"
              onClick={() => handleLeave(currentFormalSect.sect_id)}
              disabled={actionLoading}
            >
              {actionLoading ? '处理中...' : '叛出师门'}
            </button>
          </div>
        )}

        {/* 游历宗门状态栏 */}
        {visitingSects.length > 0 && (
          <div className="sect-visiting-bar">
            <span className="sect-visiting-label">游历中：</span>
            {visitingSects.map(s => (
              <span key={s.sect_id} className="sect-visiting-tag">
                {s.name}
                <Link
                  to={`/sects/resources?sect_id=${s.sect_id}`}
                  className="sect-visiting-link"
                  title="宗门秘籍"
                >秘籍↗</Link>
                <Link
                  to={`/sects/quests?sect_id=${s.sect_id}`}
                  className="sect-visiting-link"
                  title="宗门任务"
                >任务↗</Link>
                <button
                  className="sect-visiting-leave"
                  onClick={() => handleLeave(s.sect_id)}
                  disabled={actionLoading}
                  title="离开游历"
                >×</button>
              </span>
            ))}
          </div>
        )}
      </div>

      {error && (
        <div className="login-error" style={{ margin: '8px 24px 0' }}>{error}</div>
      )}

      {/* 门派卡片列表 */}
      <div className="sect-card-list">
        {sects.length === 0 && (
          <div className="empty-msg" style={{ padding: '40px 0' }}>暂无可加入的宗门</div>
        )}

        {sects.map(sect => {
          const isFormal = sect.membership_type === 'formal'
          const isVisiting = sect.membership_type === 'visiting'
          const isAnyMember = isFormal || isVisiting

          return (
            <div key={sect.sect_id} className={`sect-card${isFormal ? ' joined' : isVisiting ? ' visiting' : ''}`}>
              <div className="sect-card-main">
                <div className="sect-card-header">
                  <div className="sect-name">{sect.name}</div>
                  {isFormal && <span className="sect-joined-badge">正式弟子</span>}
                  {isVisiting && <span className="sect-visiting-badge">游历中</span>}
                </div>
                <div className="sect-tagline">{sect.tagline}</div>
                <div className="sect-focus-tags">
                  {sect.focus.map(f => (
                    <span key={f} className="focus-tag">{f}</span>
                  ))}
                </div>
                <div className="sect-meta">
                  <span
                    className="sect-difficulty"
                    style={{ color: DIFFICULTY_COLOR[sect.difficulty] || 'var(--text-dim)' }}
                  >
                    难度：{sect.difficulty}
                  </span>
                  <span className="sect-recommended">适合：{sect.recommended_for}</span>
                </div>

                {/* 宗门功法列表（已加入的宗门才显示） */}
                {isAnyMember && sectTechMap[sect.sect_id] && sectTechMap[sect.sect_id].length > 0 && (
                  <div className="sect-tech-list">
                    <div className="sect-tech-list-title">宗门功法</div>
                    {sectTechMap[sect.sect_id].map(t => (
                      <div key={t.name} className="sect-tech-item">
                        <div className="sect-tech-item-info">
                          <span className="sect-tech-item-name">{t.name}</span>
                          <span className="sect-tech-item-reward">+{t.spiritual_energy_reward} 灵气</span>
                        </div>
                        <div className="sect-tech-item-action">
                          {isFormal ? (
                            <span className="sect-tech-added-badge">已添加</span>
                          ) : t.is_added ? (
                            <span className="sect-tech-added-badge">已添加 ✓</span>
                          ) : (
                            <button
                              className="btn btn-ghost btn-xs"
                              onClick={() => handleAddTech(sect.sect_id, t.name)}
                              disabled={actionLoading}
                            >
                              添加到功课
                            </button>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div className="sect-card-action">
                {isAnyMember ? (
                  isFormal ? (
                    <button className="btn btn-ghost btn-sm" disabled>已拜入</button>
                  ) : (
                    <div className="sect-visiting-card-actions">
                      <span className="sect-visiting-badge">游历中</span>
                      <Link
                        to={`/sects/resources?sect_id=${sect.sect_id}`}
                        className="btn btn-sm sect-action-visiting"
                      >查看秘籍</Link>
                      <Link
                        to={`/sects/quests?sect_id=${sect.sect_id}`}
                        className="btn btn-sm sect-action-visiting"
                      >查看任务</Link>
                    </div>
                  )
                ) : (
                  <div className="sect-join-buttons">
                    <button
                      className="btn btn-primary btn-sm"
                      onClick={() => setConfirmSect({ sect, joinType: 'formal' })}
                      disabled={actionLoading}
                    >
                      拜入门下
                    </button>
                    <button
                      className="btn btn-ghost btn-sm"
                      onClick={() => setConfirmSect({ sect, joinType: 'visiting' })}
                      disabled={actionLoading}
                    >
                      游历参观
                    </button>
                  </div>
                )}
              </div>
            </div>
          )
        })}
      </div>

      {/* 确认弹窗 */}
      {confirmSect && (
        <div className="modal-overlay" onClick={e => e.target === e.currentTarget && setConfirmSect(null)}>
          <div className="modal">
            <div>
              <div className="modal-title">
                {confirmSect.joinType === 'formal' ? `拜入${confirmSect.sect.name}` : `游历${confirmSect.sect.name}`}
              </div>
              <div className="modal-sub">{confirmSect.sect.tagline}</div>
            </div>
            <div style={{ fontSize: 13, color: 'var(--text-dim)', lineHeight: 1.8 }}>
              {confirmSect.joinType === 'formal' ? (
                <>
                  加入后将自动添加本门修炼功法。退出宗门时，门派功法将一并移除。
                  {currentFormalSect && (
                    <span style={{ color: 'var(--gold-dim)', display: 'block', marginTop: 6 }}>
                      ⚠ 当前已正式拜入「{currentFormalSect.name}」，只能有一个正式师门，请先叛出。
                    </span>
                  )}
                </>
              ) : (
                <>
                  以游历修士身份入宗，可阅览入门典籍。
                  <span style={{ color: 'var(--text-dim)', display: 'block', marginTop: 6 }}>
                    游历不添加门派功法，不占用正式师门名额，可同时游历多个宗门。
                  </span>
                </>
              )}
            </div>
            {error && <div className="login-error">{error}</div>}
            <div className="modal-actions">
              <button className="btn btn-ghost" onClick={() => setConfirmSect(null)} disabled={actionLoading}>
                再想想
              </button>
              <button
                className="btn btn-primary"
                onClick={handleJoin}
                disabled={actionLoading || (confirmSect.joinType === 'formal' && !!currentFormalSect)}
              >
                {actionLoading
                  ? '处理中...'
                  : confirmSect.joinType === 'formal' ? '确认拜入' : '确认游历'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 欢迎消息弹窗 */}
      {welcomeMsg && (
        <div className="modal-overlay" onClick={() => setWelcomeMsg('')}>
          <div className="modal">
            <div className="modal-title">
              {welcomeType === 'formal' ? '欢迎加入宗门' : '游历登记完成'}
            </div>
            <div style={{ fontSize: 14, color: 'var(--text)', lineHeight: 1.85, whiteSpace: 'pre-wrap' }}>
              {welcomeMsg}
            </div>
            <div className="modal-actions">
              {welcomeType === 'formal' && currentFormalSect && (
                <Link
                  to={`/sects/resources?sect_id=${currentFormalSect.sect_id}`}
                  className="btn btn-gold btn-sm"
                  onClick={() => setWelcomeMsg('')}
                >
                  查阅宗门秘籍
                </Link>
              )}
              <button className="btn btn-primary" onClick={() => setWelcomeMsg('')}>
                {welcomeType === 'formal' ? '开始修炼' : '继续游览'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
