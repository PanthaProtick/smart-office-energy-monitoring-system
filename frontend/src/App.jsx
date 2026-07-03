import { useEffect, useMemo, useRef, useState } from 'react'
import './App.css'

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? ''
const WS_URL = import.meta.env.VITE_WS_URL

const formatPower = (value) => `${Number(value || 0).toFixed(1)} W`

const formatTime = (value) => {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'

  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'medium',
  }).format(date)
}

const safeJson = (value) => {
  if (!value) return null
  try {
    return typeof value === 'string' ? JSON.parse(value) : value
  } catch {
    return value
  }
}

const getWebSocketUrl = () => {
  if (WS_URL) {
    return WS_URL
  }

  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//127.0.0.1:8000/ws`
}

function App() {
  const [devices, setDevices] = useState([])
  const [rooms, setRooms] = useState([])
  const [alerts, setAlerts] = useState([])
  const [power, setPower] = useState({ total_power: 0, recent_logs: [] })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [wsStatus, setWsStatus] = useState('connecting')
  const [lastEvent, setLastEvent] = useState(null)
  const socketRef = useRef(null)
  const reconnectTimerRef = useRef(null)
  const mountedRef = useRef(true)
  const reconnectAttemptsRef = useRef(0)

  const metrics = useMemo(() => {
    const activeDevices = devices.filter((device) => device.is_active).length
    const activeAlerts = alerts.filter((alert) => alert.status === 'active').length
    return {
      totalDevices: devices.length,
      activeDevices,
      activeAlerts,
      totalPower: power.total_power ?? 0,
    }
  }, [devices, alerts, power.total_power])

  const deviceGroups = useMemo(() => {
    const grouped = rooms.map((room) => ({ room, devices: [] }))
    const fallback = []

    devices.forEach((device) => {
      const roomGroup = grouped.find((entry) => entry.room.id === device.room_id)
      if (roomGroup) {
        roomGroup.devices.push(device)
      } else {
        fallback.push(device)
      }
    })

    return [...grouped, ...(fallback.length ? [{ room: null, devices: fallback }] : [])]
  }, [devices, rooms])

  const upsertDevice = (incoming) => {
    if (!incoming?.id) return
    setDevices((current) => {
      const index = current.findIndex((device) => device.id === incoming.id)
      if (index === -1) return [incoming, ...current]
      const next = [...current]
      next[index] = { ...next[index], ...incoming }
      return next
    })
  }

  const upsertAlert = (incoming) => {
    if (!incoming?.id) return
    setAlerts((current) => {
      const index = current.findIndex((alert) => alert.id === incoming.id)
      if (index === -1) return [incoming, ...current]
      const next = [...current]
      next[index] = { ...next[index], ...incoming }
      return next
    })
  }

  const handleMessage = (event) => {
    try {
      const message = JSON.parse(event.data)
      setLastEvent({ type: message.type, data: message.data, receivedAt: new Date().toISOString() })

      if (message.type === 'device_updated') {
        upsertDevice(message.data)
      }

      if (message.type === 'power_updated') {
        setPower((current) => ({ ...current, total_power: message.data?.total_power ?? current.total_power }))
      }

      if (message.type === 'alert_created') {
        upsertAlert(message.data)
      }
    } catch {
      // ignore malformed messages
    }
  }

  const connectWebSocket = () => {
    const socketUrl = getWebSocketUrl()
    const socket = new WebSocket(socketUrl)
    socketRef.current = socket

    socket.onopen = () => {
      reconnectAttemptsRef.current = 0
      setWsStatus('connected')
      socket.send(JSON.stringify({ type: 'subscribe', event_type: 'device_updated' }))
      socket.send(JSON.stringify({ type: 'subscribe', event_type: 'power_updated' }))
      socket.send(JSON.stringify({ type: 'subscribe', event_type: 'alert_created' }))
    }

    socket.onmessage = handleMessage

    socket.onerror = () => {
      setWsStatus('error')
    }

    socket.onclose = () => {
      if (!mountedRef.current) return

      setWsStatus('disconnected')
      const attempt = reconnectAttemptsRef.current + 1
      reconnectAttemptsRef.current = attempt
      const delay = Math.min(5000, 1000 * attempt)
      reconnectTimerRef.current = window.setTimeout(connectWebSocket, delay)
    }
  }

  const loadInitialData = async () => {
    setLoading(true)
    setError('')

    try {
      const [devicesRes, roomsRes, powerRes, alertsRes] = await Promise.all([
        fetch(`${API_BASE}/devices`),
        fetch(`${API_BASE}/rooms`),
        fetch(`${API_BASE}/power`),
        fetch(`${API_BASE}/alerts/history`),
      ])

      if (!devicesRes.ok || !roomsRes.ok || !powerRes.ok || !alertsRes.ok) {
        throw new Error('Failed to load dashboard data')
      }

      const [devicesData, roomsData, powerData, alertsData] = await Promise.all([
        devicesRes.json(),
        roomsRes.json(),
        powerRes.json(),
        alertsRes.json(),
      ])

      if (!mountedRef.current) return

      setDevices(devicesData)
      setRooms(roomsData)
      setPower(powerData)
      setAlerts(alertsData)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load dashboard data')
    } finally {
      if (mountedRef.current) {
        setLoading(false)
      }
    }
  }

  useEffect(() => {
    mountedRef.current = true
    loadInitialData()
    connectWebSocket()

    return () => {
      mountedRef.current = false
      if (reconnectTimerRef.current) {
        window.clearTimeout(reconnectTimerRef.current)
      }
      socketRef.current?.close()
    }
  }, [])

  return (
    <main className="dashboard-shell">
      <header className="hero-panel">
        <div>
          <p className="eyebrow">Smart Office Energy Monitoring</p>
          <h1>Live dashboard, no polling.</h1>
          <p className="hero-copy">
            Initial data is loaded once from REST, then the UI stays synchronized
            through WebSocket events for devices, power, and alerts.
          </p>
        </div>
        <div className={`connection-pill connection-${wsStatus}`}>
          <span className="pulse" />
          <strong>{wsStatus}</strong>
          <span>WebSocket stream</span>
        </div>
      </header>

      <section className="metrics-grid">
        <article className="metric-card">
          <span>Total power</span>
          <strong>{formatPower(metrics.totalPower)}</strong>
          <small>Updated in real time</small>
        </article>
        <article className="metric-card">
          <span>Active devices</span>
          <strong>
            {metrics.activeDevices}/{metrics.totalDevices}
          </strong>
          <small>Synced from device updates</small>
        </article>
        <article className="metric-card">
          <span>Active alerts</span>
          <strong>{metrics.activeAlerts}</strong>
          <small>Resolved alerts remain in history</small>
        </article>
        <article className="metric-card">
          <span>Rooms</span>
          <strong>{rooms.length}</strong>
          <small>Loaded once from REST</small>
        </article>
      </section>

      <section className="content-grid">
        <div className="panel panel-wide">
          <div className="panel-header">
            <div>
              <p className="section-label">Rooms & devices</p>
              <h2>Device status</h2>
            </div>
            <p className="muted">Live updates arrive over WebSocket</p>
          </div>

          {loading ? (
            <div className="empty-state">Loading dashboard data…</div>
          ) : error ? (
            <div className="empty-state error-state">{error}</div>
          ) : (
            <div className="room-list">
              {deviceGroups.map((group) => (
                <section className="room-card" key={group.room?.id ?? 'fallback'}>
                  <div className="room-card-header">
                    <div>
                      <p className="section-label">
                        {group.room ? group.room.name : 'Unassigned devices'}
                      </p>
                      <h3>
                        {group.room
                          ? `${group.devices.filter((device) => device.is_active).length}/${group.devices.length} active`
                          : `${group.devices.length} device(s)`}
                      </h3>
                    </div>
                    {group.room && (
                      <span className="badge">{group.room.device_count} planned</span>
                    )}
                  </div>

                  <div className="device-grid">
                    {group.devices.map((device) => (
                      <article
                        key={device.id}
                        className={`device-card ${device.is_active ? 'device-on' : 'device-off'}`}
                      >
                        <div className="device-topline">
                          <strong>{device.name}</strong>
                          <span>{device.type}</span>
                        </div>
                        <p>{formatPower(device.power_rating)}</p>
                        <small>Last updated {formatTime(device.last_updated)}</small>
                      </article>
                    ))}
                  </div>
                </section>
              ))}
            </div>
          )}
        </div>

        <aside className="sidebar">
          <section className="panel">
            <div className="panel-header">
              <div>
                <p className="section-label">Power</p>
                <h2>Latest readings</h2>
              </div>
            </div>
            <div className="reading-list">
              {(power.recent_logs ?? []).slice(0, 6).map((entry) => (
                <div className="reading-row" key={entry.id}>
                  <span>{formatTime(entry.timestamp)}</span>
                  <strong>{formatPower(entry.total_power)}</strong>
                </div>
              ))}
              {!power.recent_logs?.length && <div className="empty-inline">No power history yet.</div>}
            </div>
          </section>

          <section className="panel">
            <div className="panel-header">
              <div>
                <p className="section-label">Alerts</p>
                <h2>Active & history</h2>
              </div>
            </div>
            <div className="alert-list">
              {alerts.slice(0, 8).map((alert) => {
                const parsedContext = safeJson(alert.context)
                return (
                  <article className={`alert-card alert-${alert.status}`} key={alert.id}>
                    <div className="alert-row">
                      <strong>{alert.rule}</strong>
                      <span>{alert.status}</span>
                    </div>
                    <p>{alert.message}</p>
                    <small>
                      Triggered {formatTime(alert.triggered_at)}
                      {alert.resolved_at ? ` • Resolved ${formatTime(alert.resolved_at)}` : ''}
                    </small>
                    {parsedContext && (
                      <pre className="alert-context">{JSON.stringify(parsedContext, null, 2)}</pre>
                    )}
                  </article>
                )
              })}
              {!alerts.length && <div className="empty-inline">No alerts yet.</div>}
            </div>
          </section>

          <section className="panel">
            <div className="panel-header">
              <div>
                <p className="section-label">Stream</p>
                <h2>Last event</h2>
              </div>
            </div>
            {lastEvent ? (
              <div className="event-card">
                <strong>{lastEvent.type}</strong>
                <pre>{JSON.stringify(lastEvent.data, null, 2)}</pre>
                <small>Received {formatTime(lastEvent.receivedAt)}</small>
              </div>
            ) : (
              <div className="empty-inline">Waiting for the first live event…</div>
            )}
          </section>
        </aside>
      </section>
    </main>
  )
}

export default App
