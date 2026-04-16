import React, { useState, useEffect } from 'react'
import { Download, Filter, Search, ShieldAlert, Clock, Info, ArrowUpRight } from 'lucide-react'
import { api } from '../api'
import { ThreatBadge, EmptyState, StatCard } from '../components/Components'
import { motion } from 'framer-motion'

export default function AlertLog() {
  const [alerts, setAlerts] = useState([])
  const [filter, setFilter] = useState('')
  const [levelFilter, setLevelFilter] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadAlerts()
  }, [levelFilter])

  async function loadAlerts() {
    setLoading(true)
    try {
      const params = { limit: 200 }
      if (levelFilter) params.level = levelFilter
      const data = await api.getAlerts(params)
      setAlerts(data)
    } catch { setAlerts([]) }
    setLoading(false)
  }

  const filtered = alerts.filter(a => {
    if (!filter) return true
    const q = filter.toLowerCase()
    return (
      (a.alert_type || '').toLowerCase().includes(q) ||
      (a.camera_id || '').toLowerCase().includes(q) ||
      (a.location_name || '').toLowerCase().includes(q) ||
      (a.threat_level || '').toLowerCase().includes(q)
    )
  })

  const highAlerts = alerts.filter(a => a.threat_level === 'HIGH').length
  const totalIncidents = alerts.length

  function exportCSV() {
    const headers = ['Time', 'Level', 'Score', 'Type', 'Camera', 'Location']
    const rows = filtered.map(a => [
      a.created_at || '', a.threat_level, a.threat_score?.toFixed(3),
      a.alert_type, a.camera_id || '', a.location_name || ''
    ])
    const csv = [headers, ...rows].map(r => r.join(',')).join('\n')
    const blob = new Blob([csv], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `safesphere_forensics_${new Date().toISOString().slice(0, 10)}.csv`
    link.click()
  }

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
      <div className="page-header" style={{ marginBottom: '40px' }}>
        <div className="flex-between">
          <div>
            <h1 style={{ fontSize: '2.5rem', fontWeight: 900, letterSpacing: '-0.04em', textTransform: 'uppercase' }}>
              Forensic Logs
            </h1>
            <p style={{ fontSize: '0.9rem', opacity: 0.7 }}>CRITICAL INCIDENT HISTORY & ANALYTICS</p>
          </div>
          <div style={{ display: 'flex', gap: '12px' }}>
            <button className="btn btn-secondary" onClick={exportCSV} style={{ borderRadius: '99px' }}>
              <Download size={14} style={{ marginRight: 8 }} /> EXPORT DB
            </button>
            <button className="btn btn-primary" onClick={loadAlerts} style={{ borderRadius: '99px' }}>
              REFRESH FEED
            </button>
          </div>
        </div>
      </div>

      <div className="stats-grid" style={{ marginBottom: '32px' }}>
        <StatCard label="Total Logged Events" value={totalIncidents} color="blue" />
        <StatCard label="Critical Breaches" value={highAlerts} color="red" />
        <StatCard label="Avg Response" value="3.2s" color="emerald" />
        <StatCard label="Storage Status" value="OPTIMIZED" color="purple" />
      </div>

      {/* Filters & Control Vault */}
      <div className="card" style={{ marginBottom: '24px', padding: '24px' }}>
        <div style={{ display: 'flex', gap: 20, alignItems: 'center', flexWrap: 'wrap' }}>
          <div style={{ flex: 1, minWidth: 280, position: 'relative' }}>
            <Search size={16} style={{ position: 'absolute', left: 16, top: '50%', transform: 'translateY(-50%)', color: 'var(--accent-blue)', opacity: 0.6 }} />
            <input
              className="input" 
              placeholder="SEARCH FORENSIC METADATA..."
              value={filter} 
              onChange={e => setFilter(e.target.value)}
              style={{ 
                paddingLeft: 48, 
                background: 'var(--bg-secondary)', 
                border: 'none',
                fontWeight: 700,
                fontSize: '0.8rem',
                textTransform: 'uppercase'
              }}
            />
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <Filter size={14} color="var(--text-muted)" />
            <select
              className="input" 
              value={levelFilter} 
              onChange={e => setLevelFilter(e.target.value)}
              style={{ 
                width: 180, 
                background: 'var(--bg-secondary)', 
                border: 'none',
                fontWeight: 800,
                fontSize: '0.75rem',
                textTransform: 'uppercase'
              }}
            >
              <option value="">ALL SIGNAL LEVELS</option>
              <option value="HIGH">CRITICAL // HIGH</option>
              <option value="MEDIUM">CAUTION // MEDIUM</option>
              <option value="LOW">STABLE // LOW</option>
              <option value="NONE">ALL CLEAR // NONE</option>
            </select>
          </div>
        </div>
      </div>

      {/* Log Table Vault */}
      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        <div className="card-header" style={{ padding: '20px 24px' }}>
          <span className="card-title" style={{ fontWeight: 800, fontSize: '0.75rem', letterSpacing: '0.1em' }}>
            INCIDENT ARCHIVE
          </span>
          <span className="text-muted text-sm" style={{ fontWeight: 700 }}>
            {filtered.length} RECORDS FOUND
          </span>
        </div>
        
        {loading ? (
          <EmptyState icon="⏳" title="Decrypting Records" description="Fetching forensic data from the secure coordinator node..." />
        ) : filtered.length > 0 ? (
          <div style={{ overflowX: 'auto' }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>TIMESTAMP</th>
                  <th>LEVEL</th>
                  <th>CONFIDENCE</th>
                  <th>CLASSIFICATION</th>
                  <th>NODE_ID</th>
                  <th>LOCUS</th>
                  <th>HUD_ALERTS</th>
                  <th style={{ width: '40px' }}></th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((a, i) => (
                  <tr key={a.id || i} style={{ borderBottom: '1px solid var(--bg-secondary)' }}>
                    <td className="mono" style={{ fontSize: '0.75rem', opacity: 0.6 }}>
                      {a.created_at ? new Date(a.created_at).toLocaleString('en-GB') : '—'}
                    </td>
                    <td><ThreatBadge level={a.threat_level} /></td>
                    <td className="mono" style={{ fontWeight: 800 }}>{(a.threat_score || 0).toFixed(3)}</td>
                    <td style={{ fontWeight: 700, textTransform: 'uppercase', fontSize: '0.75rem' }}>{a.alert_type}</td>
                    <td className="mono" style={{ fontSize: '0.7rem', opacity: 0.5 }}>{a.camera_id?.slice(0, 12)}...</td>
                    <td style={{ fontSize: '0.75rem', fontWeight: 600 }}>{a.location_name || 'UNDEFINED'}</td>
                    <td>
                      <div style={{ display: 'flex', gap: '8px' }}>
                        {a.notified_user && <div title="User Notified" style={{ color: 'var(--accent-blue)' }}><Clock size={14} /></div>}
                        {a.notified_family && <div title="Family Notified" style={{ color: 'var(--accent-amber)' }}><ShieldAlert size={14} /></div>}
                        {a.notified_security && <div title="Security Dispatched" style={{ color: 'var(--accent-red)' }}><Info size={14} /></div>}
                      </div>
                    </td>
                    <td>
                      <ArrowUpRight size={14} style={{ opacity: 0.3, cursor: 'pointer' }} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <EmptyState icon="📋" title="Vault Empty" description="Adjust your filters or initiate scanning to populate the database." />
        )}
      </div>
    </motion.div>
  )
}
