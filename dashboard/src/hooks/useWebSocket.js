/**
 * useWebSocket.js — Auto-reconnecting WebSocket hook with Exponential Backoff
 */
import { useState, useEffect, useRef, useCallback } from 'react'

const INITIAL_RECONNECT_DELAY = 1000
const MAX_RECONNECT_DELAY = 30000
const PING_INTERVAL_MS = 25000

export function useWebSocket(url) {
  const [isConnected, setIsConnected] = useState(false)
  const [lastMessage, setLastMessage] = useState(null)
  const [messages, setMessages] = useState([])
  const wsRef = useRef(null)
  const reconnectTimer = useRef(null)
  const pingTimer = useRef(null)
  const reconnectAttempt = useRef(0)

  const connect = useCallback(() => {
    if (!url) return
    
    // Cleanup previous instance before connecting
    if (wsRef.current) {
        wsRef.current.onopen = null
        wsRef.current.onclose = null
        wsRef.current.onmessage = null
        wsRef.current.onerror = null
        wsRef.current.close()
    }

    try {
      const ws = new WebSocket(url)
      wsRef.current = ws

      ws.onopen = () => {
        setIsConnected(true)
        reconnectAttempt.current = 0
        if (reconnectTimer.current) clearTimeout(reconnectTimer.current)
        
        pingTimer.current = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) ws.send('ping')
        }, PING_INTERVAL_MS)
      }

      ws.onmessage = (event) => {
        if (event.data === 'pong') return
        try {
          const data = JSON.parse(event.data)
          setLastMessage(data)
          setMessages(prev => [...prev.slice(-99), data])
        } catch { /* ignore non-JSON */ }
      }

      ws.onclose = () => {
        setIsConnected(false)
        clearInterval(pingTimer.current)
        
        // Exponential backoff
        const delay = Math.min(INITIAL_RECONNECT_DELAY * Math.pow(2, reconnectAttempt.current), MAX_RECONNECT_DELAY)
        reconnectTimer.current = setTimeout(() => {
          reconnectAttempt.current += 1
          connect()
        }, delay)
      }

      ws.onerror = () => ws.close()
    } catch (err) { 
        console.debug('WS Connection failed', err)
    }
  }, [url])

  useEffect(() => {
    connect()
    return () => {
      clearTimeout(reconnectTimer.current)
      clearInterval(pingTimer.current)
      if (wsRef.current) {
          wsRef.current.onopen = null
          wsRef.current.onclose = null
          wsRef.current.onmessage = null
          wsRef.current.onerror = null
          wsRef.current.close()
      }
    }
  }, [connect])

  const sendMessage = useCallback((data) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(typeof data === 'string' ? data : JSON.stringify(data))
    }
  }, [])

  return { isConnected, lastMessage, messages, sendMessage }
}
