import { useEffect, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { getCultivatorSects, getSectQuests } from '../api'
import { getAuth } from '../auth'
import { useTheme } from '../ThemeContext'

// 任务进度百分比（保护上限 100%）
function progressPct(current, target) {
  if (!target) return 0
  return Math.min(100, Math.round((current / target) * 100))
}

// 任务类型标签
const TYPE_LABEL = { long_term: '长期', seasonal: '限定' }
const TYPE_COLOR = { long_term: 'var(--cyan)', seasonal: 'var(--gold)' }

// 条件类型中文名（进度显示用）
function criteriaLabel(type, current, target) {
  if (type === 'checkin_count') return `已完成 ${current} / ${target} 次`
  if (type === 'streak_days') return `当前连续 ${current} / ${target} 天`
  if (type === 'total_days') return `累计修炼 ${current} / ${target} 天`
  if (type === 'total_spiritual_energy') return `累计灵气 ${current} / ${target}`
  return `进度 ${current} / ${target}`
}

function QuestCard({ quest }) {
  const pct = progressPct(quest.current_progress, quest.criteria_target)
  const isSpecial = !!quest.reward_title
  const locked = !quest.can_participate

  return (
    <div className={`quest-card${quest.is_completed ? ' quest-done' : ''}${locked ? ' quest-locked' : ''}`}>
      <div className="quest-card-header">
        <div className="quest-title-row">
          {locked && <span className="quest-lock-icon">🔒</span>}
          <span className="quest-title">{quest.title}</span>
          <span className="quest-type-tag" style={{ color: TYPE_COLOR[quest.type] || 'var(--text-dim)' }}>
            {TYPE_LABEL[quest.type] || quest.type}
          </span>
          {isSpecial && <span className="quest-special-tag">特别任务</span>}
          {quest.is_completed && <span className="quest-done-badge">已完成 ✓</span>}
        </div>
        <div className="quest-desc">{quest.description}</div>
      </div>

      <div className="quest-progress-area">
        <div className="quest-criteria">{criteriaLabel(quest.criteria_type, quest.current_progress, quest.criteria_target)}</div>
        <div className="quest-progress-bar-wrap">
          <div className="quest-progress-bar">
            <div className="quest-progress-fill" style={{ width: `${pct}%` }} />
          </div>
        </div>
      </div>

      <div className="quest-reward-row">
        <span className="quest-reward">奖励：{quest.reward_spiritual_energy} 灵气</span>
        {quest.reward_title && (
          <span className="quest-reward-title">+ 称号「{quest.reward_title}」</span>
        )}
      </div>

      {locked && quest.restrict_reason && (
        <div className="quest-restrict-note">{quest.restrict_reason}</div>
      )}
    </div>
  )
}

export default function SectQuests() {
  const auth = getAuth()
  const { theme, toggleTheme } = useTheme()
  const location = useLocation()

  // 支持 ?sect_id=xxx 查询参数（从宗门页跳转时传入）
  const params = new URLSearchParams(location.search)
  const defaultSectId = params.get('sect_id') || null

  const [sects, setSects] = useState([])      // 修士所有宗门 (formal + visiting)
  const [selectedSectId, setSelectedSectId] = useState(defaultSectId)
  const [questData, setQuestData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  // 加载修士所有宗门
  useEffect(() => {
    getCultivatorSects(auth.cultivator_id)
      .then(d => {
        const all = []
        if (d.formal) all.push({ ...d.formal, membership_type: 'formal' })
        d.visiting.forEach(v => all.push({ ...v, membership_type: 'visiting' }))
        setSects(all)
        // 默认选第一个宗门（优先正式）
        if (!selectedSectId && all.length > 0) {
          setSelectedSectId(all[0].sect_id)
        }
      })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [auth.cultivator_id])

  // 加载选中宗门的任务
  useEffect(() => {
    if (!selectedSectId) return
    setQuestData(null)
    getSectQuests(selectedSectId, auth.cultivator_id)
      .then(d => setQuestData(d))
      .catch(e => setError(e.message))
  }, [selectedSectId, auth.cultivator_id])

  if (loading) return <div className="loading-center">正在查询宗门任务...</div>

  const completedCount = questData ? questData.quests.filter(q => q.is_completed).length : 0
  const totalCount = questData ? questData.quests.length : 0

  return (
    <div className="sect-hall">
      {/* 顶部导航栏 */}
      <header className="dash-header">
        <Link to="/sects" className="btn btn-ghost btn-sm">← 门派大厅</Link>
        <span className="dash-logo">宗门任务</span>
        <div className="dash-header-spacer" />
        <Link
          to={selectedSectId ? `/sects/resources?sect_id=${selectedSectId}` : '/sects/resources'}
          className="btn btn-ghost btn-sm"
        >宗门秘籍</Link>
        <button className="btn btn-ghost btn-sm" onClick={toggleTheme}>
          {theme === 'dark' ? '亮色' : '暗色'}
        </button>
      </header>

      {/* 宗门选择标签（多宗门时显示） */}
      {sects.length > 1 && (
        <div className="quest-sect-tabs">
          {sects.map(s => (
            <button
              key={s.sect_id}
              className={`quest-sect-tab${selectedSectId === s.sect_id ? ' active' : ''}`}
              onClick={() => setSelectedSectId(s.sect_id)}
            >
              {s.name}
              {s.membership_type === 'visiting' && (
                <span className="sect-visiting-badge" style={{ marginLeft: 4 }}>游历</span>
              )}
            </button>
          ))}
        </div>
      )}

      {sects.length === 0 && !error && (
        <div className="empty-msg" style={{ padding: '60px 0', textAlign: 'center' }}>
          <div style={{ fontSize: 40, marginBottom: 12 }}>⛩</div>
          <div>尚未加入任何宗门</div>
          <Link to="/sects" className="btn btn-primary btn-sm" style={{ marginTop: 16 }}>
            前往门派大厅
          </Link>
        </div>
      )}

      {error && <div className="login-error" style={{ margin: '16px 24px' }}>{error}</div>}

      {/* 游历身份提示栏 */}
      {questData?.membership_type === 'visiting' && (
        <div className="visiting-notice">
          <span className="visiting-notice-dot">◈</span>
          游历身份 · 可参与普通任务，特别任务（含称号奖励）需正式拜入后解锁
        </div>
      )}

      {/* 任务列表 */}
      {questData && (
        <div className="sect-hall-title">
          <div className="quest-header-row">
            <div>
              <div className="sect-hall-h1">{questData.sect_name}</div>
              <div className="sect-hall-sub">
                {questData.membership_type === 'visiting' ? '游历修士任务' : '正式弟子任务'}
                {totalCount > 0 && (
                  <span style={{ marginLeft: 10, color: 'var(--text-muted)', fontSize: 12 }}>
                    已完成 {completedCount} / {totalCount}
                  </span>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {questData && questData.quests.length === 0 && (
        <div className="empty-msg" style={{ padding: '40px 0' }}>该宗门暂无任务</div>
      )}

      {questData && (
        <div className="sect-card-list">
          {questData.quests.map(q => (
            <QuestCard key={q.quest_id} quest={q} />
          ))}
        </div>
      )}

      {!questData && selectedSectId && !error && (
        <div className="loading-center" style={{ paddingTop: 40 }}>加载任务中...</div>
      )}
    </div>
  )
}
