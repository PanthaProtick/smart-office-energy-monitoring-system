import { useEffect, useMemo, useRef, useState } from 'react'
import './App.css'
import fanIcon from './assets/fan.png'
import lightIcon from './assets/lamp.png'

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? ''
const WS_URL = import.meta.env.VITE_WS_URL

const formatPower = (value) => `${Number(value || 0).toFixed(1)} W`

const formatEnergy = (value) => `${Number(value || 0).toFixed(2)} Wh`

const formatTime = (value) => {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'

  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(date)
}

const getFanSpinDuration = (powerRating) => {
  const watts = Number(powerRating || 0)

  if (!watts) return '0s'
  if (watts >= 90) return '1.6s'
  if (watts >= 70) return '2.1s'
  if (watts >= 40) return '2.8s'
  return '3.6s'
}

const getDeviceKind = (type) => String(type || '').toLowerCase()

const getWebSocketUrl = () => {
  if (WS_URL) {
    return WS_URL
  }

  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//127.0.0.1:8000/ws`
}

function DeviceVisual({ device }) {
  const kind = getDeviceKind(device.type)

  if (kind === 'fan') {
    return (
      <div className={`fan-visual ${device.is_active ? 'fan-visual-on' : 'fan-visual-off'}`}>
        <img className="fan-image" src={fanIcon} alt="" aria-hidden="true" />
      </div>
    )
  }

  return (
    <div className={`light-visual ${device.is_active ? 'light-visual-on' : 'light-visual-off'}`}>
      <img className="light-image" src={lightIcon} alt="" aria-hidden="true" />
    </div>
  )
}

function App() {
  const [devices, setDevices] = useState([])
  const [rooms, setRooms] = useState([])
  const [alerts, setAlerts] = useState([])
  const [power, setPower] = useState({ total_power: 0, recent_logs: [] })
  const [energy, setEnergy] = useState({ total_power_usage_wh: 0, predicted_power_usage_wh: 0 })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [wsStatus, setWsStatus] = useState('connecting')
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
      totalEnergy: energy.total_power_usage_wh ?? 0,
      predictedEnergy: energy.predicted_power_usage_wh ?? 0,
    }
  }, [devices, alerts, power.total_power, energy.total_power_usage_wh, energy.predicted_power_usage_wh])

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

      if (message.type === 'device_updated') {
        upsertDevice(message.data)
      }

      if (message.type === 'power_updated') {
        setPower((current) => ({
          ...current,
          total_power: message.data?.total_power ?? current.total_power,
        }))
        setEnergy((current) => ({
          ...current,
          total_power_usage_wh:
            message.data?.total_power_usage_wh ?? current.total_power_usage_wh,
          predicted_power_usage_wh:
            message.data?.predicted_power_usage_wh ?? current.predicted_power_usage_wh,
        }))
      }

      if (message.type === 'energy_updated') {
        setEnergy((current) => ({
          ...current,
          total_power_usage_wh:
            message.data?.total_power_usage_wh ?? current.total_power_usage_wh,
          predicted_power_usage_wh:
            message.data?.predicted_power_usage_wh ?? current.predicted_power_usage_wh,
        }))
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
      socket.send(JSON.stringify({ type: 'subscribe', event_type: 'energy_updated' }))
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
      setEnergy({
        total_power_usage_wh: powerData.total_power_usage_wh ?? 0,
        predicted_power_usage_wh: powerData.predicted_power_usage_wh ?? 0,
      })
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
      <header className="topbar">
        <div className="brand">
          <p className="eyebrow">Smart Office Energy Monitoring</p>
          <h1>Dashboard</h1>
        </div>
        <div className={`connection-pill connection-${wsStatus}`}>
          <span className="pulse" />
          <strong>{wsStatus}</strong>
        </div>
      </header>

      <section className="metrics-grid">
        <article className="metric-card">
          <span>Total power</span>
          <strong>{formatPower(metrics.totalPower)}</strong>
        </article>
        <article className="metric-card">
          <span>Energy used</span>
          <strong>{formatEnergy(metrics.totalEnergy)}</strong>
        </article>
        <article className="metric-card">
          <span>Predicted daily energy</span>
          <strong>{formatEnergy(metrics.predictedEnergy)}</strong>
        </article>
        <article className="metric-card">
          <span>Active devices</span>
          <strong>
            {metrics.activeDevices}/{metrics.totalDevices}
          </strong>
        </article>
        <article className="metric-card">
          <span>Active alerts</span>
          <strong>{metrics.activeAlerts}</strong>
        </article>
        <article className="metric-card">
          <span>Rooms</span>
          <strong>{rooms.length}</strong>
        </article>
      </section>

      <section className="rooms-hero">
        {loading ? (
          <div className="empty-state">Loading dashboard data…</div>
        ) : error ? (
          <div className="empty-state error-state">{error}</div>
        ) : (
          <div className="room-columns">
            {deviceGroups.map((group) => (
              <section className="room-card" key={group.room?.id ?? 'fallback'}>
                <div className="room-card-header">
                  <p className="section-label">
                    {group.room ? group.room.name : 'Unassigned devices'}
                  </p>
                  <h3>
                    {group.room
                      ? `${group.devices.filter((device) => device.is_active).length}/${group.devices.length} active`
                      : `${group.devices.length} device(s)`}
                  </h3>
                </div>

                <div className="device-grid">
                  {group.devices.map((device) => (
                    <article
                      key={device.id}
                      className={`device-card device-${getDeviceKind(device.type) || 'generic'} ${device.is_active ? 'device-on' : 'device-off'}`}
                      style={{
                        '--fan-duration': getFanSpinDuration(device.power_rating),
                        '--glow-strength': device.is_active
                          ? Math.max(0.5, Math.min(1.1, Number(device.power_rating || 0) / 80 || 0.6))
                          : 0,
                      }}
                    >
                      <div className="device-visual" aria-hidden="true">
                        <DeviceVisual device={device} />
                      </div>
                      <div className="device-meta">
                        <strong>{device.name}</strong>
                        <span>{formatPower(device.power_rating)}</span>
                      </div>
                    </article>
                  ))}
                </div>
              </section>
            ))}
          </div>
        )}
      </section>

      <section className="alerts-strip">
        <div className="panel-header">
          <p className="section-label">Recent alerts</p>
        </div>
        <div className="alert-list-compact">
          {alerts.slice(0, 2).map((alert) => (
            <article className={`alert-card alert-${alert.status}`} key={alert.id}>
              <div className="alert-row">
                <strong>{alert.rule}</strong>
                <span>{alert.status}</span>
              </div>
              <p>{alert.message}</p>
              <small>{formatTime(alert.triggered_at)}</small>
            </article>
          ))}
          {!alerts.length && <div className="empty-inline">No alerts yet.</div>}
        </div>
      </section>
    </main>
  )
}

export default App
