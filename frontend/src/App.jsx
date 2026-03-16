import { useEffect, useState } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import './index.css'
import { getAuth } from './auth'
import { ThemeContext } from './ThemeContext'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Dialogue from './pages/Dialogue'
import Sects from './pages/Sects'
import SectResources from './pages/SectResources'
import SectQuests from './pages/SectQuests'
import History from './pages/History'

function PrivateRoute({ children }) {
  return getAuth() ? children : <Navigate to="/login" replace />
}

export default function App() {
  const [theme, setTheme] = useState(
    () => localStorage.getItem('selfup_theme') || 'dark'
  )

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    localStorage.setItem('selfup_theme', theme)
  }, [theme])

  function toggleTheme() {
    setTheme(t => (t === 'dark' ? 'light' : 'dark'))
  }

  return (
    <ThemeContext.Provider value={{ theme, toggleTheme }}>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route
            path="/dashboard"
            element={<PrivateRoute><Dashboard /></PrivateRoute>}
          />
          <Route
            path="/dialogue"
            element={<PrivateRoute><Dialogue /></PrivateRoute>}
          />
          <Route
            path="/sects"
            element={<PrivateRoute><Sects /></PrivateRoute>}
          />
          <Route
            path="/sects/resources"
            element={<PrivateRoute><SectResources /></PrivateRoute>}
          />
          <Route
            path="/sects/quests"
            element={<PrivateRoute><SectQuests /></PrivateRoute>}
          />
          <Route
            path="/history"
            element={<PrivateRoute><History /></PrivateRoute>}
          />
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
        </Routes>
      </BrowserRouter>
    </ThemeContext.Provider>
  )
}
