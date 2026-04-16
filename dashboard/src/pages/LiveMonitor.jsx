import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import { Activity, AlertTriangle, Users, Shield, Wifi, WifiOff, Video, VideoOff, Eye, Cpu, Database, Binary, Zap } from 'lucide-react'
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'
import { api, WS_URL } from '../api'
import { useWebSocket } from '../hooks/useWebSocket'
import { StatCard, ThreatBadge, EmptyState } from '../components/Components'

/**
 * LiveVideoFeed — Displays processed camera frames from the edge processor.
 * Optimized with requestAnimationFrame for smoother performance.
 */
/**
 * LiveVideoFeed — Displays processed camera frames for a specific node.
 */
function LiveVideoFeed({ cameraId, frame, latency, isConnected }) {
  const imgRef = useRef(null);

  useEffect(() => {
    if (frame && imgRef.current) {
      imgRef.current.src = frame;
    }
  }, [frame]);

  return (
    <div className="card" style={{ padding: 0, background: 'var(--bg-primary)', overflow: 'hidden', height: '100%' }}>
      <div style={{
        background: '#040812',
        position: 'relative',
        height: '100%',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        minHeight: 300
      }}>
        {/* HUD Graphics */}
        <div className="scan-line" />
        <div className="tactical-corners" />

        {isConnected && frame ? (
          <>
            <img
              ref={imgRef}
              alt={`Feed ${cameraId}`}
              style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }}
            />
            <div style={{
              position: 'absolute', top: 16, left: 16, zIndex: 20,
              display: 'flex', flexDirection: 'column', gap: 8
            }}>
              <div style={{ 
                background: 'rgba(5, 10, 20, 0.85)', padding: '4px 10px', borderRadius: 4,
                fontSize: 9, fontWeight: 900, color: 'var(--accent-blue)', letterSpacing: '0.15em',
                backdropFilter: 'blur(12px)', borderLeft: '3px solid var(--accent-blue)'
              }}>
                NODE_STREAM::{cameraId.toUpperCase()}
              </div>
              <div style={{ 
                background: 'rgba(5, 10, 20, 0.85)', padding: '4px 10px', borderRadius: 4,
                fontSize: 8, fontWeight: 900, color: 'var(--accent-emerald)', letterSpacing: '0.1em',
                backdropFilter: 'blur(12px)', borderLeft: '3px solid var(--accent-emerald)',
                display: 'flex', alignItems: 'center', gap: 6
              }}>
                <Zap size={8} /> {latency}ms LATENCY
              </div>
            </div>
          </>
        ) : (
          <div style={{ textAlign: 'center', color: 'var(--text-muted)' }}>
            <VideoOff size={40} style={{ marginBottom: 16, opacity: 0.2, color: 'var(--accent-blue)' }} />
            <div style={{ fontSize: 10, fontWeight: 900, color: 'var(--text-primary)', letterSpacing: '0.1em' }}>
              WAITING_FOR_UPLINK::{cameraId.toUpperCase()}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

const AlertRow = React.memo(({ alert }) => {
  const getLevelColor = (l) => {
    if (l === 'HIGH') return 'var(--accent-red)';
    if (l === 'MEDIUM') return 'var(--accent-amber)';
    return 'var(--accent-blue)';
  }

  return (
    <tr>
      <td className="mono" style={{ color: 'var(--text-muted)' }}>
        {new Date(alert.created_at).toLocaleTimeString().slice(0, 8)}
      </td>
      <td>
        <span style={{ 
          fontSize: '9px', fontWeight: 900, letterSpacing: '1px', 
          color: getLevelColor(alert.threat_level),
          background: getLevelColor(alert.threat_level) + '15',
          padding: '2px 8px', borderRadius: '4px', border: `1px solid ${getLevelColor(alert.threat_level)}40`
        }}>
          {alert.threat_level}
        </span>
      </td>
      <td className="mono" style={{ fontWeight: 700 }}>{Math.round(alert.threat_score * 100)}%</td>
      <td style={{ fontWeight: 600 }}>{alert.threat_type?.toUpperCase() || 'UNKNOWN'}</td>
      <td className="mono" style={{ color: 'var(--accent-blue)', fontSize: '10px' }}>{alert.camera_id?.slice(0,8) || 'NODE-AUX'}</td>
    </tr>
  )
})

export default function LiveMonitor() {
  const [stats, setStats] = useState({ cameras: 0, journeys: 0, alerts: 0, persons: 0 })
  const [cameraNodes, setCameraNodes] = useState([])
  const [recentAlerts, setRecentAlerts] = useState([])
  const [activeJourneys, setActiveJourneys] = useState([])
  const [threatHistory, setThreatHistory] = useState([])
  const [systemLogs, setSystemLogs] = useState(['BOOT_SYS_COMMAND...', 'CORE_LOADED'])
  
  // Multi-stream management
  const [feeds, setFeeds] = useState({}); // camera_id -> { frame, latency }
  const { isConnected, lastMessage } = useWebSocket(`${WS_URL}/ws/dashboard`)
  const feedWs = useRef(null);

  useEffect(() => {
    const ws = new WebSocket(`${WS_URL}/ws/processed-feed`);
    feedWs.current = ws;
    ws.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data);
        if (data.type === 'frame_update') {
          const latency = Math.round(performance.now() - (data.timestamp * 1000) % performance.now());
          setFeeds(prev => ({
            ...prev,
            [data.camera_id]: { frame: data.frame, latency }
          }));
        }
      } catch (err) { /* ignore binary or malformed */ }
    }
    return () => ws.close();
  }, []);

  useEffect(() => {
    loadData()
    const intv = setInterval(loadData, 5000);
    const logIntv = setInterval(() => {
      const logs = ['NODE_04_PULSE', 'VRAM_GC_OK', 'GPS_SYNC_11ms', 'TELEM_HUB_ALIVE'];
      setSystemLogs(prev => [logs[Math.floor(Math.random() * logs.length)], ...prev].slice(0, 3));
    }, 4000);
    return () => { clearInterval(intv); clearInterval(logIntv); }
  }, [])

  useEffect(() => {
    if (lastMessage?.type === 'threat_alert') {
      setRecentAlerts(prev => [lastMessage, ...prev].slice(0, 20))
      setThreatHistory(prev => [
        ...prev.slice(-29),
        { time: new Date().toLocaleTimeString().slice(0, 5), score: lastMessage.threat_score }
      ])
    }
  }, [lastMessage])

  async function loadData() {
    try {
      const [camerasRes, alertsRes, journeysRes] = await Promise.allSettled([
        api.getCameras(),
        api.getAlerts({ limit: 20 }),
        api.getActiveJourneys(),
      ])
      const cams = camerasRes.status === 'fulfilled' ? camerasRes.value : []
      const alts = alertsRes.status === 'fulfilled' ? alertsRes.value : []
      const jrns = journeysRes.status === 'fulfilled' ? journeysRes.value : []
      setCameraNodes(cams)
      setRecentAlerts(alts)
      setActiveJourneys(jrns)
      setStats({
        cameras: cams.filter(c => c.status === 'online').length,
        journeys: jrns.length,
        alerts: alts.filter(a => ['MEDIUM', 'HIGH'].includes(a.threat_level)).length,
        persons: cams.reduce((sum, c) => sum + (c.person_count || 0), 0),
      })
    } catch { /* silence */ }
  }

  // Force a 50/50 split for the dual-node demo
  const gridStyle = { gridTemplateColumns: '1fr 1fr' };
  const expectedNodes = ['phone_node_01', 'phone_node_02'];

  return (
    <div style={{ maxWidth: '1600px', margin: '0 auto' }}>
      <div className="page-header" style={{ marginBottom: '40px' }}>
        <div className="flex-between">
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 8 }}>
              <div style={{ 
                background: 'var(--accent-blue)', width: 12, height: 12, borderRadius: 2,
                boxShadow: '0 0 10px var(--accent-blue-glow)'
              }} className="pulse-indicator" />
              <span style={{ fontSize: '10px', fontWeight: 900, letterSpacing: '4px', color: 'var(--accent-blue)' }}>TACTICAL HUD</span>
            </div>
            <h1 style={{ fontSize: '3.5rem', fontWeight: 900, letterSpacing: '-0.04em', lineHeight: 1 }}>
              COMMAND CENTER
            </h1>
          </div>
          <div className="card" style={{ padding: '12px 24px', borderRadius: '16px', background: 'var(--bg-secondary)' }}>
            <div className="flex-between gap-md">
              <div style={{ textAlign: 'right' }}>
                <div style={{ fontSize: '10px', fontWeight: 900, color: 'var(--text-muted)' }}>LINK_STATUS</div>
                <div style={{ fontSize: '12px', fontWeight: 900, color: isConnected ? 'var(--accent-emerald)' : 'var(--accent-red)' }}>
                  {isConnected ? 'STABLE' : 'RECONNECTING'}
                </div>
              </div>
              <Wifi size={24} color={isConnected ? 'var(--accent-emerald)' : 'var(--text-muted)'} className={!isConnected ? 'pulse-indicator' : ''} />
            </div>
          </div>
        </div>
      </div>

      <div className="stats-grid">
        <StatCard label="Live Nodes" value={stats.cameras} color="blue" />
        <StatCard label="Active HUDs" value={stats.journeys} color="blue" />
        <StatCard label="Anomalies" value={stats.alerts} color={stats.alerts > 0 ? 'red' : 'emerald'} />
        <StatCard label="Identities" value={stats.persons} color="purple" />
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 400px', gap: '32px' }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '32px' }}>
          
          {/* Camera Feed Grid */}
          <div style={{ 
            display: 'grid', 
            gap: '20px',
            ...gridStyle,
            minHeight: 520
          }}>
            {expectedNodes.map(cid => (
                <LiveVideoFeed 
                  key={cid}
                  cameraId={cid}
                  frame={feeds[cid]?.frame}
                  latency={feeds[cid]?.latency || '--'}
                  isConnected={isConnected && !!feeds[cid]?.frame}
                />
            ))}
          </div>

          <div className="card">
            <div className="card-header">
               <div>
                  <div className="card-title">FORENSIC_SIGNAL_LOG</div>
                  <div className="text-muted text-sm">REAL-TIME ANOMALY DETECTION ENGINE</div>
               </div>
               <div className="flex-center gap-sm">
                  <span className="threat-badge none">FILTER: ALL</span>
               </div>
            </div>
            <div style={{ maxHeight: '350px', overflow: 'auto' }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>TIMESTAMP</th>
                    <th>LEVEL</th>
                    <th>CONF</th>
                    <th>ANOMALY_TYPE</th>
                    <th>SOURCE_NODE</th>
                  </tr>
                </thead>
                <tbody>
                  {recentAlerts.length > 0 ? (
                    recentAlerts.map((a, i) => <AlertRow key={a.id || i} alert={a} />)
                  ) : (
                    <tr><td colSpan="5" style={{ textAlign: 'center', padding: '40px', color: 'var(--text-muted)' }}>NO ANOMALIES RECORDED</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '32px' }}>
          {/* Threat Kinematics */}
          <div className="card">
            <div className="card-header">
              <div className="card-title">KINEMATIC_THREAT_GRAPH</div>
              <Activity size={16} color="var(--accent-red)" className="pulse-indicator" />
            </div>
            <div style={{ height: 180, marginTop: 20 }}>
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={threatHistory}>
                  <defs>
                    <linearGradient id="threatFill" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="var(--accent-red)" stopOpacity={0.4} />
                      <stop offset="95%" stopColor="var(--accent-red)" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <Tooltip 
                    contentStyle={{ background: 'var(--bg-secondary)', border: 'none', borderRadius: 8, fontSize: 10, fontWeight: 800 }} 
                  />
                  <Area type="monotone" dataKey="score" stroke="var(--accent-red)" fill="url(#threatFill)" strokeWidth={3} isAnimationActive={false} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
            <div style={{ marginTop: 24 }}>
               <div style={{ fontSize: '9px', fontWeight: 900, color: 'var(--text-muted)', marginBottom: 8 }}>HARDWARE_STREAMS</div>
               {systemLogs.map((log, i) => (
                 <div key={i} style={{ 
                   fontSize: '10px', fontFamily: 'JetBrains Mono', color: 'var(--accent-blue)', 
                   opacity: 1 - (i * 0.3), marginBottom: 4 
                 }}>
                   {`> [${new Date().toLocaleTimeString()}] ${log}`}
                 </div>
               ))}
            </div>
          </div>

          {/* Active Guardian Networks */}
          <div className="card" style={{ flex: 1 }}>
            <div className="card-header">
              <div className="card-title">EN_ROUTE_GUARDIANS</div>
              <div className="threat-badge none">{activeJourneys.length} ACTIVE</div>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginTop: 20 }}>
              {activeJourneys.length > 0 ? (
                activeJourneys.map(j => (
                  <div key={j.id} style={{
                    padding: '20px', background: 'var(--bg-secondary)', borderRadius: '16px',
                    borderLeft: '4px solid var(--accent-blue)'
                  }}>
                    <div className="flex-between">
                      <div style={{ fontSize: '11px', fontWeight: 900, color: 'var(--text-primary)' }}>
                        ID: {j.id.slice(0,8).toUpperCase()}
                      </div>
                      <Shield size={16} color="var(--accent-blue)" />
                    </div>
                    <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: 8, fontWeight: 600 }}>
                      DEST: {j.end_address?.toUpperCase() || 'SAFE_ZONE'}
                    </div>
                    <div style={{ marginTop: 12, display: 'flex', gap: 6 }}>
                       <div style={{ width: 6, height: 6, borderRadius: 3, background: 'var(--accent-emerald)' }} className="pulse-indicator" />
                       <span style={{ fontSize: '9px', fontWeight: 900, color: 'var(--accent-emerald)' }}>UPLINK ACTIVE</span>
                    </div>
                  </div>
                ))
              ) : (
                <div style={{ textAlign: 'center', padding: '40px', color: 'var(--text-muted)' }}>
                  <Users size={32} style={{ marginBottom: 12, opacity: 0.2 }} />
                  <div style={{ fontSize: '11px', fontWeight: 800 }}>NO ACTIVE TELEMETRY</div>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
