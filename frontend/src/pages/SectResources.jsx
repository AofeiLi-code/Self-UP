import { useEffect, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { getCultivatorSects, getSectResources } from '../api'
import { getAuth } from '../auth'
import { useTheme } from '../ThemeContext'

// ── 资源类型标签 ─────────────────────────────────────────────
const TYPE_LABEL = { article: '文章', video_link: '视频', schedule: '计划表' }

// ── 推荐境界小标签 ────────────────────────────────────────────
function RealmBadge({ realm }) {
  if (!realm) return null
  return (
    <div className="resource-realm-row">
      <span className="resource-realm-badge">推荐境界：{realm}</span>
    </div>
  )
}

// ── 文章 ──────────────────────────────────────────────────────
function ArticleResource({ resource }) {
  const [expanded, setExpanded] = useState(false)

  return (
    <div className="resource-card">
      {!resource.is_recommended && <RealmBadge realm={resource.recommended_realm} />}
      <div className="resource-card-header" onClick={() => setExpanded(e => !e)}>
        <div>
          <span className="resource-type-badge article">文章</span>
          <div className="resource-title">{resource.title}</div>
        </div>
        <span className="expand-icon">{expanded ? '▲' : '▼'}</span>
      </div>
      {expanded && (
        <div className="resource-article-body">{resource.content}</div>
      )}
    </div>
  )
}

// ── 视频链接 ──────────────────────────────────────────────────
function VideoResource({ resource }) {
  return (
    <div className="resource-card">
      {!resource.is_recommended && <RealmBadge realm={resource.recommended_realm} />}
      <span className="resource-type-badge video">视频</span>
      <div className="resource-title">{resource.title}</div>
      {resource.content && (
        <div className="resource-desc">{resource.content}</div>
      )}
      {resource.url && (
        <a
          href={resource.url}
          target="_blank"
          rel="noopener noreferrer"
          className="btn btn-ghost btn-sm"
          style={{ marginTop: 10, display: 'inline-flex' }}
        >
          前往观看 →
        </a>
      )}
    </div>
  )
}

// ── 修炼计划表 ────────────────────────────────────────────────
function ScheduleResource({ resource }) {
  let schedule = {}
  try { schedule = JSON.parse(resource.content) } catch { /* ignore */ }

  const entries = Object.entries(schedule)
  const isNested = entries.length > 0 && typeof entries[0][1] === 'object'

  return (
    <div className="resource-card">
      {!resource.is_recommended && <RealmBadge realm={resource.recommended_realm} />}
      <span className="resource-type-badge schedule">计划表</span>
      <div className="resource-title">{resource.title}</div>

      {isNested ? (
        <div className="schedule-sections">
          {entries.map(([section, items]) => (
            <div key={section} className="schedule-section">
              <div className="schedule-section-title">{section}</div>
              <table className="schedule-table">
                <tbody>
                  {Object.entries(items).map(([time, activity]) => (
                    <tr key={time}>
                      <td className="schedule-time">{time}</td>
                      <td className="schedule-activity">{String(activity)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}
        </div>
      ) : (
        <table className="schedule-table" style={{ marginTop: 12 }}>
          <tbody>
            {entries.map(([day, activity]) => (
              <tr key={day}>
                <td className="schedule-time">{day}</td>
                <td className="schedule-activity">{String(activity)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

// ── 主页面 ────────────────────────────────────────────────────
export default function SectResources() {
  const auth = getAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const { theme, toggleTheme } = useTheme()

  const params = new URLSearchParams(location.search)
  const defaultSectId = params.get('sect_id') || null

  const [sects, setSects] = useState([])           // 修士所有宗门（正式 + 游历）
  const [selectedSectId, setSelectedSectId] = useState(defaultSectId)
  const [data, setData] = useState(null)
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
        if (!selectedSectId && all.length > 0) setSelectedSectId(all[0].sect_id)
        if (all.length === 0) navigate('/sects', { replace: true })
      })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [auth.cultivator_id])

  // 加载选中宗门的秘籍
  useEffect(() => {
    if (!selectedSectId) return
    setData(null)
    getSectResources(auth.cultivator_id, selectedSectId)
      .then(res => setData(res))
      .catch(e => setError(e.message))
  }, [selectedSectId, auth.cultivator_id])

  if (loading) return <div className="loading-center">正在加载宗门秘籍...</div>

  if (error) {
    return (
      <div className="loading-center" style={{ flexDirection: 'column', gap: 12 }}>
        <div style={{ color: 'var(--danger)' }}>{error}</div>
        <Link to="/sects" className="btn btn-ghost btn-sm">返回门派大厅</Link>
      </div>
    )
  }

  function renderResource(r) {
    if (r.type === 'article') return <ArticleResource key={r.resource_id} resource={r} />
    if (r.type === 'video_link') return <VideoResource key={r.resource_id} resource={r} />
    if (r.type === 'schedule') return <ScheduleResource key={r.resource_id} resource={r} />
    return null
  }

  const isVisiting = data?.membership_type === 'visiting'
  const total = data?.resources.length ?? 0
  const sorted = data
    ? [...data.resources].sort((a, b) => {
        if (a.is_recommended === b.is_recommended) return 0
        return a.is_recommended ? -1 : 1
      })
    : []

  return (
    <div className="resources-page">
      {/* 顶部导航 */}
      <header className="dash-header">
        <Link to="/sects" className="btn btn-ghost btn-sm">← 返回</Link>
        <span className="dash-logo">宗门秘籍</span>
        <div className="dash-header-spacer" />
        <Link
          to={selectedSectId ? `/sects/quests?sect_id=${selectedSectId}` : '/sects/quests'}
          className="btn btn-ghost btn-sm"
        >宗门任务</Link>
        <button className="btn btn-ghost btn-sm" onClick={toggleTheme}>
          {theme === 'dark' ? '亮色' : '暗色'}
        </button>
      </header>

      {/* 宗门切换标签（多宗门时显示） */}
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

      {/* 宗门信息头 */}
      {data && (
        <div className="resources-page-header">
          <span className="resources-page-title">{data.sect_name}</span>
          <span className="resources-page-realm">{data.cultivator_realm}</span>
          <div style={{ flex: 1 }} />
          <Link to="/dashboard" className="btn btn-ghost btn-sm" style={{ fontSize: 11 }}>
            返回修炼台
          </Link>
        </div>
      )}

      {/* 游历身份提示栏 */}
      {isVisiting && (
        <div className="visiting-notice">
          <span className="visiting-notice-dot">◈</span>
          游历身份 · 可查看全部秘籍，拜入门下后可解锁成就与特别任务
        </div>
      )}

      {/* 内容加载中 */}
      {!data && selectedSectId && !error && (
        <div className="loading-center" style={{ paddingTop: 40 }}>加载秘籍中...</div>
      )}

      {/* 资源统计 + 列表 */}
      {data && (
        <>
          {total > 0 && (
            <div className="resources-stat">
              共 {total} 份秘籍，{data.recommended_count} 份适合当前境界
            </div>
          )}
          <div className="resources-list">
            {total === 0 && (
              <div className="empty-msg" style={{ padding: '40px 0' }}>本宗门暂无秘籍</div>
            )}
            {sorted.map(r => renderResource(r))}
          </div>
        </>
      )}
    </div>
  )
}
