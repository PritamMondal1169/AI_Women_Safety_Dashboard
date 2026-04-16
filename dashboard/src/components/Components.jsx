import React from 'react'

export function ThreatBadge({ level }) {
  const cls = (level || 'none').toLowerCase()
  return (
    <span className={`threat-badge ${cls}`}>
      <span style={{
        width: 6, height: 6, borderRadius: '50%',
        background: 'currentColor', display: 'inline-block',
      }} />
      {(level || 'NONE').toUpperCase()}
    </span>
  )
}

export function StatCard({ label, value, color = 'blue', change, changeType }) {
  return (
    <div className={`card stat-card ${color}`} style={{ padding: '24px' }}>
      <div className="stat-label" style={{ 
        textTransform: 'uppercase', 
        letterSpacing: '0.1em', 
        fontSize: '0.65rem',
        fontWeight: 800,
        marginBottom: '12px',
        opacity: 0.8
      }}>
        {label}
      </div>
      <div className="stat-value" style={{ 
        fontSize: '2.5rem', 
        fontWeight: 900, 
        fontFamily: 'Inter',
        letterSpacing: '-0.02em'
      }}>
        {value}
      </div>
      {change !== undefined && (
        <span className={`stat-change ${changeType || 'positive'}`} style={{ marginTop: '16px' }}>
          {changeType === 'negative' ? '↓' : '↑'} {change}
        </span>
      )}
    </div>
  )
}

export function CameraCard({ camera }) {
  const statusCls = (camera.status || 'offline').toLowerCase()
  return (
    <div className="card camera-card">
      <div className="camera-header">
        <span className="camera-name" style={{ fontWeight: 700 }}>{camera.name}</span>
        <span className={`camera-status ${statusCls}`} style={{ fontSize: '0.7rem', fontWeight: 800 }}>
          <span className={`status-dot ${statusCls}`} />
          {camera.status?.toUpperCase()}
        </span>
      </div>
      <div className="camera-stats" style={{ marginTop: '20px' }}>
        <div className="camera-stat">
          <span className="camera-stat-label">Frame Rate</span>
          <span className="camera-stat-value">{camera.fps?.toFixed(1) || '0.0'} FPS</span>
        </div>
        <div className="camera-stat">
          <span className="camera-stat-label">Detections</span>
          <span className="camera-stat-value">{camera.person_count ?? 0} PERSONS</span>
        </div>
      </div>
    </div>
  )
}

export function AlertRow({ alert, onClick }) {
  const time = alert.created_at
    ? new Date(alert.created_at).toLocaleTimeString()
    : '—'
  return (
    <tr onClick={onClick} style={{ cursor: onClick ? 'pointer' : 'default' }}>
      <td className="mono" style={{ opacity: 0.7 }}>{time}</td>
      <td><ThreatBadge level={alert.threat_level} /></td>
      <td className="mono" style={{ fontWeight: 700 }}>{alert.threat_score?.toFixed(3)}</td>
      <td style={{ fontWeight: 500 }}>{alert.alert_type}</td>
      <td className="mono" style={{ opacity: 0.6 }}>{alert.camera_id?.slice(0, 8) || '—'}</td>
    </tr>
  )
}

export function EmptyState({ icon, title, description }) {
  return (
    <div className="flex-center" style={{ 
      flexDirection: 'column', 
      padding: '80px 40px', 
      gap: 16,
      textAlign: 'center'
    }}>
      <div style={{ fontSize: 48, filter: 'grayscale(1) brightness(2)', opacity: 0.2 }}>{icon || '📡'}</div>
      <h3 style={{ fontWeight: 800, color: 'var(--text-primary)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
        {title}
      </h3>
      <p className="text-muted text-sm" style={{ maxWidth: '240px' }}>{description}</p>
    </div>
  )
}
