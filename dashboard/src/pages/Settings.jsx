import React, { useState, useEffect } from 'react'
import { Settings as SettingsIcon, Save, Zap, Database, ShieldCheck, Activity, Globe, Cpu } from 'lucide-react'
import { api } from '../api'
import { motion } from 'framer-motion'

export default function Settings() {
  const [thresholds, setThresholds] = useState({
    low: 0.35,
    medium: 0.60,
    high: 0.80,
  })
  const [coordinatorStatus, setCoordinatorStatus] = useState(null)

  useEffect(() => {
    checkHealth()
  }, [])

  async function checkHealth() {
    try {
      const data = await api.health()
      setCoordinatorStatus(data)
    } catch {
      setCoordinatorStatus(null)
    }
  }

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
      <div className="page-header" style={{ marginBottom: '40px' }}>
        <div className="flex-between">
          <div>
            <h1 style={{ fontSize: '2.5rem', fontWeight: 900, letterSpacing: '-0.04em', textTransform: 'uppercase' }}>
              System Configuration
            </h1>
            <p style={{ fontSize: '0.9rem', opacity: 0.7 }}>CORE PROTOCOLS & THRESHOLD MANAGEMENT</p>
          </div>
          <button className="btn btn-primary" style={{ borderRadius: '99px' }}>
            <Save size={14} style={{ marginRight: 8 }} /> PUSH CONFIG
          </button>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '32px' }}>
        {/* Threat Thresholds */}
        <div className="card" style={{ padding: '24px' }}>
          <div className="card-header" style={{ marginBottom: '24px' }}>
            <span className="card-title" style={{ fontWeight: 800, fontSize: '0.75rem', letterSpacing: '0.1em' }}>
              THREAT SENSITIVITY MATRIX
            </span>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '32px' }}>
            <div className="slider-container">
              <div className="slider-header" style={{ marginBottom: '12px' }}>
                <span className="slider-label" style={{ fontWeight: 700, fontSize: '0.75rem', opacity: 0.6 }}>LOW SIGNAL THRESHOLD</span>
                <span className="slider-value" style={{ fontWeight: 800, fontFamily: 'monospace' }}>{thresholds.low.toFixed(2)}</span>
              </div>
              <input
                type="range" min="0.1" max="0.5" step="0.01"
                value={thresholds.low}
                onChange={e => setThresholds(p => ({ ...p, low: +e.target.value }))}
                style={{ width: '100%', accentColor: 'var(--accent-blue)' }}
              />
            </div>

            <div className="slider-container">
              <div className="slider-header" style={{ marginBottom: '12px' }}>
                <span className="slider-label" style={{ fontWeight: 700, fontSize: '0.75rem', opacity: 0.6 }}>MEDIUM SIGNAL THRESHOLD</span>
                <span className="slider-value" style={{ color: 'var(--accent-amber)', fontWeight: 800, fontFamily: 'monospace' }}>{thresholds.medium.toFixed(2)}</span>
              </div>
              <input
                type="range" min="0.3" max="0.8" step="0.01"
                value={thresholds.medium}
                onChange={e => setThresholds(p => ({ ...p, medium: +e.target.value }))}
                style={{ width: '100%', accentColor: 'var(--accent-amber)' }}
              />
            </div>

            <div className="slider-container">
              <div className="slider-header" style={{ marginBottom: '12px' }}>
                <span className="slider-label" style={{ fontWeight: 700, fontSize: '0.75rem', opacity: 0.6 }}>CRITICAL SIGNAL THRESHOLD</span>
                <span className="slider-value" style={{ color: 'var(--accent-red)', fontWeight: 800, fontFamily: 'monospace' }}>{thresholds.high.toFixed(2)}</span>
              </div>
              <input
                type="range" min="0.5" max="1.0" step="0.01"
                value={thresholds.high}
                onChange={e => setThresholds(p => ({ ...p, high: +e.target.value }))}
                style={{ width: '100%', accentColor: 'var(--accent-red)' }}
              />
            </div>
          </div>
        </div>

        {/* System Health Panel */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
          <div className="card" style={{ padding: '24px' }}>
            <div className="card-header" style={{ marginBottom: '24px' }}>
              <span className="card-title" style={{ fontWeight: 800, fontSize: '0.75rem', letterSpacing: '0.1em' }}>
                REAL-TIME SYSTEM HEARTBEAT
              </span>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              <div style={{ 
                background: 'var(--bg-secondary)', 
                padding: '16px', 
                borderRadius: '12px',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center'
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                  <Globe size={16} color="var(--accent-blue)" />
                  <span style={{ fontWeight: 700, fontSize: '0.85rem' }}>COORDINATOR CLOUD</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span style={{ fontSize: '0.65rem', fontWeight: 800, color: coordinatorStatus ? 'var(--accent-emerald)' : 'var(--accent-red)' }}>
                    {coordinatorStatus ? 'OPERATIONAL' : 'LINK SEVERED'}
                  </span>
                  <span className={`status-dot ${coordinatorStatus ? 'online' : 'offline'}`} />
                </div>
              </div>

              <div style={{ 
                background: 'var(--bg-secondary)', 
                padding: '16px', 
                borderRadius: '12px',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center'
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                  <Cpu size={16} color="var(--accent-blue)" />
                  <span style={{ fontWeight: 700, fontSize: '0.85rem' }}>EDGE INFERENCE ENGINE</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span style={{ fontSize: '0.65rem', fontWeight: 800, color: 'var(--accent-emerald)' }}>STABLE</span>
                  <span className="status-dot online" />
                </div>
              </div>

              <div style={{ 
                background: 'var(--bg-secondary)', 
                padding: '16px', 
                borderRadius: '12px',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center'
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                  <Database size={16} color="var(--accent-purple)" />
                  <span style={{ fontWeight: 700, fontSize: '0.85rem' }}>FORENSIC STORAGE</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span style={{ fontSize: '0.65rem', fontWeight: 800, color: 'var(--accent-emerald)' }}>OPTIMIZED (84% FREE)</span>
                  <span className="status-dot online" />
                </div>
              </div>
            </div>
            
            <button className="btn btn-secondary mt-lg" onClick={checkHealth} style={{ width: '100%', borderRadius: '12px' }}>
              <Zap size={14} style={{ marginRight: 8 }} /> FORCE SYSTEM SYNC
            </button>
          </div>
        </div>
      </div>

      {/* Protocol Index */}
      <div className="card mt-lg" style={{ padding: 0, overflow: 'hidden' }}>
        <div className="card-header" style={{ padding: '20px 24px' }}>
          <span className="card-title" style={{ fontWeight: 800, fontSize: '0.75rem', letterSpacing: '0.1em' }}>
            API PROTOCOL DOCUMENTATION
          </span>
        </div>
        <table className="data-table">
          <thead>
            <tr>
              <th>CLASS</th>
              <th>ENDPOINT_ADDR</th>
              <th>LOGIC_PAYLOAD</th>
              <th>PERMISSIONS</th>
            </tr>
          </thead>
          <tbody>
            {[
              ['SECURE', '/api/v1/auth/identity', 'Multifactor Verification', 'ANONYMOUS'],
              ['TRACK', '/api/v1/journey/init', 'Kinematic Vector Initialization', 'USER_IDENTIFIED'],
              ['ALERT', '/api/v1/signal/escalate', 'Asymmetric Threat Scoring', 'EDGE_NODE'],
              ['FEEDS', '/ws/guardian/live', 'Bidirectional Encrypted Socket', 'DASHBOARD'],
              ['LOGS', '/api/v1/forensics/query', 'Historical Metadata Retrieval', 'SECURITY_ADMIN'],
            ].map(([cls, path, desc, perm], i) => (
              <tr key={i} style={{ borderBottom: '1px solid var(--bg-secondary)' }}>
                <td>
                  <span style={{ 
                    padding: '4px 8px', 
                    background: 'var(--bg-secondary)', 
                    borderRadius: '4px', 
                    fontSize: '0.6rem', 
                    fontWeight: 900,
                    color: 'var(--accent-blue)'
                  }}>
                    {cls}
                  </span>
                </td>
                <td className="mono" style={{ fontSize: '0.75rem', fontWeight: 600 }}>{path}</td>
                <td style={{ fontSize: '0.8rem', opacity: 0.7 }}>{desc}</td>
                <td style={{ fontSize: '0.65rem', fontWeight: 800, opacity: 0.5 }}>{perm}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </motion.div>
  )
}
