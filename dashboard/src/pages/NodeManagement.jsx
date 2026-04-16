import React, { useState, useEffect } from 'react'
import { Server, Zap, HardDrive, Cpu, Layers, Link as LinkIcon, AlertCircle, CheckCircle2 } from 'lucide-react'
import { api } from '../api'
import { StatCard, ThreatBadge } from '../components/Components'
import { motion } from 'framer-motion'

export default function NodeManagement() {
  const [nodes, setNodes] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadNodes()
    const intv = setInterval(loadNodes, 5000)
    return () => clearInterval(intv)
  }, [])

  async function loadNodes() {
    try {
      const data = await api.getCameras()
      setNodes(data)
    } catch { /* coordinator offline */ }
    setLoading(false)
  }

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
      <div className="page-header" style={{ marginBottom: '40px' }}>
        <div className="flex-between">
          <div>
            <h1 style={{ fontSize: '2.5rem', fontWeight: 900, letterSpacing: '-0.04em', textTransform: 'uppercase' }}>
              Node Management
            </h1>
            <p style={{ fontSize: '0.9rem', opacity: 0.7 }}>EDGE INFRASTRUCTURE & BLIND-SPOT LINKS</p>
          </div>
          <div style={{ display: 'flex', gap: '12px' }}>
            <button className="btn btn-secondary" style={{ borderRadius: '99px' }}>
               PROVISION NEW NODE
            </button>
          </div>
        </div>
      </div>

      <div className="grid-3" style={{ marginBottom: '32px' }}>
        <StatCard label="Provisioned Nodes" value={nodes.length} color="blue" />
        <StatCard label="Network Throughput" value="1.2 Gbps" color="emerald" />
        <StatCard label="Blind Spots Coverage" value="94%" color="purple" />
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
        {nodes.map(node => (
          <div key={node.id} className="card" style={{ padding: '24px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '24px' }}>
              <div style={{ display: 'flex', gap: '20px', alignItems: 'center' }}>
                <div style={{ 
                  width: '56px', height: '56px', 
                  background: 'var(--bg-secondary)', 
                  borderRadius: '16px',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  border: '1px solid var(--glass-border)'
                }}>
                  <Server size={28} color="var(--accent-blue)" />
                </div>
                <div>
                  <h3 style={{ fontSize: '1.2rem', fontWeight: 800 }}>{node.name}</h3>
                  <div style={{ display: 'flex', gap: '12px', alignItems: 'center', marginTop: '4px' }}>
                     <span style={{ fontSize: '0.7rem', fontWeight: 800, color: 'var(--text-muted)' }}>ID: {node.id.toUpperCase()}</span>
                     <span style={{ width: '4px', height: '4px', borderRadius: '50%', background: 'var(--text-muted)' }} />
                     <span style={{ fontSize: '0.7rem', fontWeight: 800, color: node.status === 'online' ? 'var(--accent-emerald)' : 'var(--accent-red)' }}>
                       {node.status.toUpperCase()}
                     </span>
                  </div>
                </div>
              </div>
              <div style={{ display: 'flex', gap: '8px' }}>
                <button className="btn btn-secondary" style={{ padding: '8px 16px', fontSize: '0.7rem', fontWeight: 800 }}>REBOOT</button>
                <button className="btn btn-primary" style={{ padding: '8px 16px', fontSize: '0.7rem', fontWeight: 800 }}>CONFIG</button>
              </div>
            </div>

            <div className="grid-4" style={{ background: 'var(--bg-secondary)', padding: '20px', borderRadius: '16px', gap: '20px' }}>
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px', opacity: 0.6 }}>
                  <Cpu size={14} />
                  <span style={{ fontSize: '0.65rem', fontWeight: 800 }}>COMPUTE LOAD</span>
                </div>
                <div style={{ fontSize: '1.2rem', fontWeight: 900 }}>{(Math.random() * 40 + 20).toFixed(1)}%</div>
              </div>
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px', opacity: 0.6 }}>
                  <Layers size={14} />
                  <span style={{ fontSize: '0.65rem', fontWeight: 800 }}>VRAM USAGE</span>
                </div>
                <div style={{ fontSize: '1.2rem', fontWeight: 900 }}>2.4 GB / 8 GB</div>
              </div>
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px', opacity: 0.6 }}>
                  <HardDrive size={14} />
                  <span style={{ fontSize: '0.65rem', fontWeight: 800 }}>SSD HEALTH</span>
                </div>
                <div style={{ fontSize: '1.2rem', fontWeight: 900 }}>98% SECTORS</div>
              </div>
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px', opacity: 0.6 }}>
                  <Zap size={14} />
                  <span style={{ fontSize: '0.65rem', fontWeight: 800 }}>POWER DRAW</span>
                </div>
                <div style={{ fontSize: '1.2rem', fontWeight: 900 }}>42W</div>
              </div>
            </div>

            {/* Blind Spot Linkage */}
            <div style={{ marginTop: '24px', display: 'flex', alignItems: 'center', gap: '16px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '10px 16px', background: 'var(--bg-secondary)', borderRadius: '99px', fontSize: '0.75rem', fontWeight: 700 }}>
                <LinkIcon size={14} color="var(--accent-blue)" />
                LINKED TO: {node.linked_camera_id ? node.linked_camera_id.slice(0, 8) : 'NONE'}
              </div>
              <button style={{ background: 'none', border: 'none', color: 'var(--accent-blue)', fontWeight: 800, fontSize: '0.7rem', cursor: 'pointer', textTransform: 'uppercase' }}>
                RECONFIGURE TOPOLOGY
              </button>
            </div>
          </div>
        ))}

        {nodes.length === 0 && !loading && (
          <div className="card" style={{ padding: '80px' }}>
            <EmptyState 
              icon={<Server size={48} />} 
              title="NO EDGE INFRASTRUCTURE" 
              description="Register new AI nodes to build your Guardian Network coverage." 
            />
          </div>
        )}
      </div>
    </motion.div>
  )
}
