import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { sendDialogue } from '../api'
import { getAuth } from '../auth'
import { useTheme } from '../ThemeContext'

const GREETING = '宿主，今日修炼如何？有何困惑或感悟，尽可与本系统倾谈。'

export default function Dialogue() {
  const auth = getAuth()
  const { theme, toggleTheme } = useTheme()
  const [messages, setMessages] = useState([])   // [{role:'user'|'system', content}]
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const bottomRef = useRef(null)
  const textareaRef = useRef(null)

  // 页面加载时展示系统问候（不发送至后端，纯本地展示）
  useEffect(() => {
    setMessages([{ role: 'system', content: GREETING }])
  }, [])

  // 每次新消息时滚动到底部
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  async function send() {
    const text = input.trim()
    if (!text || loading) return
    setInput('')
    setMessages(prev => [...prev, { role: 'user', content: text }])
    setLoading(true)
    try {
      const data = await sendDialogue(auth.cultivator_id, text)
      setMessages(prev => [...prev, { role: 'system', content: data.reply }])
    } catch (err) {
      setMessages(prev => [...prev, { role: 'system', content: `[系统异常：${err.message}]` }])
    } finally {
      setLoading(false)
    }
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      send()
    }
  }

  // 自动调整 textarea 高度
  function handleInput(e) {
    setInput(e.target.value)
    const el = e.target
    el.style.height = 'auto'
    el.style.height = Math.min(el.scrollHeight, 120) + 'px'
  }

  return (
    <div className="dialogue-page">
      {/* 顶部栏 */}
      <header className="dialogue-header">
        <Link to="/dashboard" className="back-btn">← 返回修炼界面</Link>
        <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>|</span>
        <span className="dialogue-sys-name">{auth.system_name ?? '随身系统'}</span>
        <div style={{ flex: 1 }} />
        <button className="btn btn-ghost btn-sm" onClick={toggleTheme}>
          {theme === 'dark' ? '亮色' : '暗色'}
        </button>
      </header>

      {/* 聊天区域 */}
      <div className="chat-area">
        {messages.map((msg, i) => (
          <div key={i} className={`bubble-row ${msg.role}`}>
            <div className={`bubble ${msg.role}`}>{msg.content}</div>
          </div>
        ))}

        {loading && (
          <div className="bubble-row system">
            <div className="bubble system bubble-thinking">
              <span className="dot" /><span className="dot" /><span className="dot" />
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* 输入栏 */}
      <div className="chat-input-bar">
        <textarea
          ref={textareaRef}
          className="chat-input"
          placeholder="向随身系统倾诉（Enter 发送，Shift+Enter 换行）"
          value={input}
          onChange={handleInput}
          onKeyDown={handleKeyDown}
          rows={1}
        />
        <button
          className="btn btn-primary"
          onClick={send}
          disabled={!input.trim() || loading}
        >
          发送
        </button>
      </div>
    </div>
  )
}
