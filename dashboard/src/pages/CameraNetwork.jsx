import React, { useState, useEffect } from 'react'
import { Camera, RefreshCw, Activity, Cpu, Database, LayoutGrid, MapPin, Radio, ShieldCheck, Zap } from 'lucide-react'
import { api } from '../api'
import { StatCard, EmptyState, ThreatBadge } from '../components/Components'
import { MapContainer, TileLayer, Marker, Popup, Circle } from 'react-leaflet'
import { motion, AnimatePresence } from 'framer-motion'
import L from 'leaflet'

// Fix for default Leaflet marker icons in React
import icon from 'leaflet/dist/images/marker-icon.png'
import iconShadow from 'leaflet/dist/images/marker-shadow.png'

let DefaultIcon = L.icon({
  iconUrl: icon,
  shadowUrl: iconShadow,
  iconSize: [25, 41],
  iconAnchor: [12, 41]
})
L.Marker.prototype.options.icon = DefaultIcon

export default function CameraNetwork() {
  const [cameras, setCameras] = useState([])
  const [selectedNode, setSelectedNode] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadData()
    const intv = setInterval(loadData, 5000)
    return () => clearInterval(intv)
  }, [])

  async function loadData() {
    try {
      const camData = await api.getCameras()
      setCameras(camData)
      if (!selectedNode && camData.length > 0) setSelectedNode(camData[0])
    } catch { /* silence */ }
    setLoading(false)
  }

  const onlineCount = cameras.filter(c => c.status === 'online').length

  return (
    <motion.div 
      initial={{ opacity: 0 }} 
      animate={{ opacity: 1 }}
      style={{ display: 'flex', flexDirection: 'column', height: 'calc(100vh - 120px)' }}
    >
      <div className="page-header" style={{ marginBottom: '40px' }}>
        <div className="flex-between">
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 8 }}>
              <Radio size={12} color="var(--accent-blue)" />
              <span style={{ fontSize: '10px', fontWeight: 900, letterSpacing: '4px', color: 'var(--accent-blue)' }}>NETWORK TOPOLOGY</span>
            </div>
            <h1 style={{ fontSize: '3.5rem', fontWeight: 900, letterSpacing: '-0.04em', lineHeight: 1 }}>
              GUARDIAN MESH
            </h1>
          </div>
          <button className="btn btn-secondary" onClick={loadData} style={{ padding: '12px 24px', borderRadius: '12px' }}>
            <RefreshCw size={14} style={{ marginRight: 8 }} /> RESCAN_NODES
          </button>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '400px 1fr', gap: '32px', flex: 1, minHeight: 0 }}>
        {/* Node Sidebar */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '32px', overflowY: 'auto', paddingRight: '12px' }}>
          <div className="card" style={{ background: 'var(--bg-secondary)', padding: '24px' }}>
            <div className="card-title" style={{ marginBottom: 20 }}>NETWORK_HEALTH</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              <div className="flex-between">
                <span className="text-muted text-sm" style={{ fontWeight: 800 }}>UPLINK NODES</span>
                <span style={{ fontWeight: 900, fontSize: '1.2rem' }}>{onlineCount}/{cameras.length}</span>
              </div>
              <div style={{ height: '6px', background: 'var(--bg-primary)', borderRadius: '3px', overflow: 'hidden' }}>
                <motion.div 
                  initial={{ width: 0 }}
                  animate={{ width: `${(onlineCount / cameras.length) * 100}%` }}
                  style={{ 
                    height: '100%', 
                    background: 'var(--accent-emerald)',
                    boxShadow: '0 0 10px var(--accent-emerald-glow)'
                  }} 
                />
              </div>
            </div>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
             <span style={{ fontSize: '10px', fontWeight: 900, color: 'var(--text-muted)', letterSpacing: '2px', marginBottom: 8 }}>NODE_SELECTION</span>
            {cameras.map(node => (
              <motion.div
                key={node.id}
                whileHover={{ x: 4 }}
                onClick={() => setSelectedNode(node)}
                style={{
                  padding: '20px',
                  background: selectedNode?.id === node.id ? 'var(--bg-card-hover)' : 'var(--bg-card)',
                  borderRadius: '24px',
                  cursor: 'pointer',
                  borderLeft: selectedNode?.id === node.id ? '6px solid var(--accent-blue)' : '6px solid transparent',
                  transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
                  boxShadow: selectedNode?.id === node.id ? '0 10px 30px rgba(0,0,0,0.3)' : 'none'
                }}
              >
                <div className="flex-between">
                  <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                     <Camera size={16} color={node.status === 'online' ? 'var(--accent-blue)' : 'var(--text-muted)'} />
                     <span style={{ fontWeight: 800, fontSize: '1rem', color: selectedNode?.id === node.id ? 'var(--text-primary)' : 'var(--text-secondary)' }}>
                        {node.name?.toUpperCase()}
                     </span>
                  </div>
                  <div style={{ 
                    width: 8, height: 8, borderRadius: 4, 
                    background: node.status === 'online' ? 'var(--accent-emerald)' : 'var(--accent-red)',
                    boxShadow: node.status === 'online' ? '0 0 10px var(--accent-emerald-glow)' : 'none'
                  }} />
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 12 }}>
                   <span style={{ fontSize: '9px', fontWeight: 900, color: 'var(--text-muted)' }}>ID: {node.id.slice(0, 12)}</span>
                   {node.alert_level !== 'NONE' && (
                     <span style={{ fontSize: '9px', fontWeight: 900, color: 'var(--accent-red)' }}>ANOMALY_DETECTED</span>
                   )}
                </div>
              </motion.div>
            ))}
          </div>
        </div>

        {/* Global Map Content */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '32px' }}>
          <div className="card" style={{ flex: 1, padding: 0, position: 'relative', overflow: 'hidden', borderRadius: '32px' }}>
            <MapContainer 
              center={[22.5726, 88.3639]} 
              zoom={14} 
              style={{ height: '100%', width: '100%' }}
              zoomControl={false}
            >
              <TileLayer
                url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
                attribution='&copy; CARTO'
              />
              {cameras.map(cam => (
                <React.Fragment key={cam.id}>
                  <Marker position={[cam.latitude || 22.5726, cam.longitude || 88.3639]}>
                    <Popup closeButton={false}>
                      <div style={{ background: 'var(--bg-primary)', color: 'var(--text-primary)', padding: '16px', borderRadius: '12px', minWidth: 140 }}>
                        <div style={{ fontSize: '10px', fontWeight: 900, color: 'var(--accent-blue)', marginBottom: 4 }}>NODE_UPLINK</div>
                        <h4 style={{ margin: 0, fontWeight: 900 }}>{cam.name}</h4>
                        <div style={{ marginTop: 12 }}>
                           <ThreatBadge level={cam.alert_level || 'NONE'} />
                        </div>
                      </div>
                    </Popup>
                  </Marker>
                  {cam.status === 'online' && (
                    <Circle 
                      center={[cam.latitude || 22.5726, cam.longitude || 88.3639]}
                      radius={400}
                      pathOptions={{ 
                        fillColor: cam.alert_level === 'HIGH' ? 'var(--accent-red)' : 'var(--accent-blue)', 
                        color: 'transparent',
                        fillOpacity: 0.08 
                      }}
                    />
                  )}
                </React.Fragment>
              ))}
            </MapContainer>
            
            {/* Map HUD Components */}
            <div style={{ position: 'absolute', top: 30, right: 30, zIndex: 1000, display: 'flex', flexDirection: 'column', gap: 16 }}>
               <div className="card" style={{ background: 'rgba(11, 19, 38, 0.8)', backdropFilter: 'blur(16px)', padding: '16px 24px', borderRadius: '20px', border: '1px solid rgba(123, 208, 255, 0.1)' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                     <Zap size={18} color="var(--accent-amber)" />
                     <div>
                        <div style={{ fontSize: '9px', fontWeight: 900, color: 'var(--text-muted)' }}>THROUGHPUT</div>
                        <div style={{ fontSize: '14px', fontWeight: 900, color: 'var(--text-primary)' }}>1.2 GB/S</div>
                     </div>
                  </div>
               </div>
               <div className="card" style={{ background: 'rgba(11, 19, 38, 0.8)', backdropFilter: 'blur(16px)', padding: '16px 24px', borderRadius: '20px', border: '1px solid rgba(123, 208, 255, 0.1)' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                     <Database size={18} color="var(--accent-blue)" />
                     <div>
                        <div style={{ fontSize: '9px', fontWeight: 900, color: 'var(--text-muted)' }}>STORAGE_ENCRYPTION</div>
                        <div style={{ fontSize: '14px', fontWeight: 900, color: 'var(--accent-emerald)' }}>ENABLED</div>
                     </div>
                  </div>
               </div>
            </div>
          </div>

          {/* Detailed Node Analytics */}
          <AnimatePresence mode="wait">
            {selectedNode && (
              <motion.div
                key={selectedNode.id}
                initial={{ y: 30, opacity: 0 }}
                animate={{ y: 0, opacity: 1 }}
                exit={{ y: 30, opacity: 0 }}
                className="card"
                style={{ padding: '32px', borderRadius: '32px', background: 'var(--bg-card)' }}
              >
                <div className="flex-between" style={{ marginBottom: '32px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '20px' }}>
                    <div style={{ background: 'var(--accent-blue-glow)', padding: '16px', borderRadius: '20px' }}>
                      <Camera size={32} color="var(--accent-blue)" />
                    </div>
                    <div>
                      <div style={{ fontSize: '10px', fontWeight: 900, color: 'var(--accent-blue)', letterSpacing: '1px' }}>SELECTED_NODE_INTEL</div>
                      <h3 style={{ fontSize: '2rem', fontWeight: 900, letterSpacing: '-0.02em' }}>{selectedNode.name?.toUpperCase()}</h3>
                    </div>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                     <ThreatBadge level={selectedNode.alert_level || 'NONE'} />
                     <div style={{ fontSize: '10px', fontWeight: 800, color: 'var(--text-muted)', marginTop: 8 }}>CORE_HW_ID: {selectedNode.id}</div>
                  </div>
                </div>

                <div className="grid-3">
                  <div style={{ background: 'var(--bg-secondary)', padding: '24px', borderRadius: '24px', border: '1px solid rgba(255,255,255,0.02)' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
                      <Activity size={16} color="var(--accent-emerald)" />
                      <span style={{ fontSize: '10px', fontWeight: 900, color: 'var(--text-muted)' }}>INFERENCE_LATENCY</span>
                    </div>
                    <div style={{ fontSize: '2rem', fontWeight: 900 }}>{selectedNode.fps?.toFixed(1) || '0.0'}<small style={{ fontSize: '0.8rem', opacity: 0.5 }}> FPS</small></div>
                  </div>
                  <div style={{ background: 'var(--bg-secondary)', padding: '24px', borderRadius: '24px', border: '1px solid rgba(255,255,255,0.02)' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
                      <Cpu size={16} color="var(--accent-blue)" />
                      <span style={{ fontSize: '10px', fontWeight: 900, color: 'var(--text-muted)' }}>SOC_UTILIZATION</span>
                    </div>
                    <div style={{ fontSize: '2rem', fontWeight: 900 }}>38%<small style={{ fontSize: '0.8rem', opacity: 0.5 }}> CPU</small></div>
                  </div>
                  <div style={{ background: 'var(--bg-secondary)', padding: '24px', borderRadius: '24px', border: '1px solid rgba(255,255,255,0.02)' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
                      <ShieldCheck size={16} color="var(--accent-purple)" />
                      <span style={{ fontSize: '10px', fontWeight: 900, color: 'var(--text-muted)' }}>ACTIVE_PROTECTIONS</span>
                    </div>
                    <div style={{ fontSize: '2rem', fontWeight: 900 }}>{selectedNode.person_count || 0}<small style={{ fontSize: '0.8rem', opacity: 0.5 }}> IDENTITIES</small></div>
                  </div>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </motion.div>
  )
}
