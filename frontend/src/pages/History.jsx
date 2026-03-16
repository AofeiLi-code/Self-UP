import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { getCultivationHistory } from '../api'
import { getAuth } from '../auth'
import { useTheme } from '../ThemeContext'

const PAGE_SIZE = 20

function formatDate(iso) {
  const d = new Date(iso)
  const y = d.getFullYear()
  const mo = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${mo}-${day}`
}

function formatTime(iso) {
  const d = new Date(iso)
  const h = String(d.getHours()).padStart(2, '0')
  const m = String(d.getMinutes()).padStart(2, '0')
  return `${h}:${m}`
}

// 把记录列表按日期（yyyy-mm-dd）分组，返回 [{date, records}]
function groupByDate(records) {
  const map = new Map()
  for (const r of records) {
    const d = formatDate(r.cultivated_at)
    if (!map.has(d)) map.set(d, [])
    map.get(d).push(r)
  }
  return Array.from(map.entries()).map(([date, recs]) => ({ date, records: recs }))
}

function Lightbox({ url, onClose }) {
  useEffect(() => {
    function onKey(e) { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div className="lightbox-overlay" onClick={onClose}>
      <img
        className="lightbox-img"
        src={url}
        alt="修炼凭证"
        onClick={e => e.stopPropagation()}
      />
      <button className="lightbox-close" onClick={onClose}>✕</button>
    </div>
  )
}

export default function History() {
  const auth = getAuth()
  const { theme, toggleTheme } = useTheme()

  const [records, setRecords] = useState([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState('')
  const [lightboxUrl, setLightboxUrl] = useState(null)
  const hasMore = records.length < total

  useEffect(() => {
    setLoading(true)
    getCultivationHistory(auth.cultivator_id, 1, PAGE_SIZE)
      .then(data => {
        setRecords(data.records)
        setTotal(data.total)
        setPage(1)
      })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [auth.cultivator_id])

  async function loadMore() {
    setLoadingMore(true)
    try {
      const next = page + 1
      const data = await getCultivationHistory(auth.cultivator_id, next, PAGE_SIZE)
      setRecords(prev => [...prev, ...data.records])
      setPage(next)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoadingMore(false)
    }
  }

  if (loading) return <div className="loading-center">正在翻阅修炼典籍...</div>

  const groups = groupByDate(records)

  return (
    <div className="history-page">
      <header className="dash-header">
        <Link to="/dashboard" className="btn btn-ghost btn-sm">← 返回</Link>
        <span className="dash-logo">修炼历史</span>
        <div className="dash-header-spacer" />
        <span className="history-total-label">共 {total} 条记录</span>
        <button className="btn btn-ghost btn-sm" onClick={toggleTheme}>
          {theme === 'dark' ? '亮色' : '暗色'}
        </button>
      </header>

      {error && <div className="login-error" style={{ margin: '12px 20px 0' }}>{error}</div>}

      {total === 0 && !error && (
        <div className="empty-msg" style={{ paddingTop: 60, textAlign: 'center' }}>
          <div style={{ fontSize: 40, marginBottom: 12 }}>📖</div>
          <div>尚无修炼记录</div>
          <Link to="/dashboard" className="btn btn-primary btn-sm" style={{ marginTop: 16 }}>
            前往修炼台
          </Link>
        </div>
      )}

      <div className="history-content">
        {groups.map(({ date, records: recs }) => (
          <div key={date} className="history-date-group">
            <div className="history-date-label">{date}</div>
            <div className="history-record-list">
              {recs.map(r => (
                <div key={r.id} className="history-record-card">
                  {r.photo_url && (
                    <div
                      className="history-thumb-wrap"
                      onClick={() => setLightboxUrl(r.photo_url)}
                      title="查看原图"
                    >
                      <img className="history-thumb" src={r.photo_url} alt="修炼凭证" />
                      <span className="history-thumb-zoom">⊕</span>
                    </div>
                  )}
                  <div className="history-record-body">
                    <div className="history-record-top">
                      <span className="history-technique-name">{r.technique_name}</span>
                      <span className="history-record-time">{formatTime(r.cultivated_at)}</span>
                      <span className="history-energy-badge">+{r.spiritual_energy_gained} 灵气</span>
                    </div>
                    {r.note && (
                      <div className="history-note">{r.note}</div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}

        {hasMore && (
          <div className="history-load-more">
            <button
              className="btn btn-ghost btn-sm"
              onClick={loadMore}
              disabled={loadingMore}
            >
              {loadingMore ? '加载中...' : `加载更多（还剩 ${total - records.length} 条）`}
            </button>
          </div>
        )}
      </div>

      {lightboxUrl && (
        <Lightbox url={lightboxUrl} onClose={() => setLightboxUrl(null)} />
      )}
    </div>
  )
}
