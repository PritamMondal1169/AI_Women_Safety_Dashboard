import React from 'react'
import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom'
import { Activity, FileWarning, Camera, Settings, Server, Shield } from 'lucide-react'
import LiveMonitor from './pages/LiveMonitor'
import AlertLog from './pages/AlertLog'
import CameraNetwork from './pages/CameraNetwork'
import SettingsPage from './pages/Settings'
import NodeManagement from './pages/NodeManagement'
import './index.css'

function App() {
  return (
    <BrowserRouter>
      <div className="app-layout">
        {/* Sidebar */}
        <aside className="sidebar">
          <div className="sidebar-brand" style={{ padding: '32px 24px', marginBottom: '16px' }}>
            <div style={{ 
              width: '40px', height: '40px', 
              background: 'var(--accent-blue-glow)', 
              borderRadius: '12px',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              marginBottom: '16px'
            }}>
              <Shield size={22} color="var(--accent-blue)" />
            </div>
            <div>
              <h1 style={{ fontSize: '1.2rem', fontWeight: 900, letterSpacing: '-0.02em', textTransform: 'uppercase' }}>
                SafeSphere
              </h1>
              <small style={{ fontSize: '0.65rem', fontWeight: 800, opacity: 0.5, letterSpacing: '0.1em' }}>
                OBSIDIAN CORE v2.1
              </small>
            </div>
          </div>

          <nav className="sidebar-nav">
            <NavLink to="/" end className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
              <Activity size={18} /> Live Monitor
            </NavLink>
            <NavLink to="/alerts" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
              <FileWarning size={18} /> Forensic Logs
            </NavLink>
            <NavLink to="/cameras" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
              <Camera size={18} /> Global Map
            </NavLink>
            <NavLink to="/nodes" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
              <Server size={18} /> Node Assets
            </NavLink>
            <div style={{ height: '32px' }} />
            <NavLink to="/settings" className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`}>
              <Settings size={18} /> Settings
            </NavLink>
          </nav>

          <div className="sidebar-status" style={{ padding: '16px 24px' }}>
            <div className="status-indicator" style={{ background: 'var(--bg-secondary)', borderRadius: '12px', padding: '12px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span className="status-dot online" />
                <span style={{ fontSize: '0.7rem', fontWeight: 800 }}>SECURE LINK UP</span>
              </div>
              <div style={{ fontSize: '0.6rem', opacity: 0.5, marginTop: '4px' }}>WSS://COORD.SAFESPHERE.LOCAL:8080</div>
            </div>
          </div>
        </aside>

        {/* Main Content */}
        <main className="main-content">
          <Routes>
            <Route path="/" element={<LiveMonitor />} />
            <Route path="/alerts" element={<AlertLog />} />
            <Route path="/cameras" element={<CameraNetwork />} />
            <Route path="/nodes" element={<NodeManagement />} />
            <Route path="/settings" element={<SettingsPage />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}

export default App
