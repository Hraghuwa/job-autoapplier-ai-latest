type EventHandler = (data: any) => void

interface WSOptions {
  maxRetries?: number
  baseDelay?: number
}

class WSManager {
  private ws: WebSocket | null = null
  private url: string = ''
  private handlers = new Map<string, Set<EventHandler>>()
  private retryCount = 0
  private maxRetries: number
  private baseDelay: number
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null
  private intentionalClose = false

  constructor(options: WSOptions = {}) {
    this.maxRetries = options.maxRetries ?? 10
    this.baseDelay = options.baseDelay ?? 1000
  }

  connect(url: string) {
    this.url = url
    this.intentionalClose = false
    this.retryCount = 0
    this._connect()
  }

  private _connect() {
    if (this.ws?.readyState === WebSocket.OPEN) return

    try {
      this.ws = new WebSocket(this.url)

      this.ws.onopen = () => {
        this.retryCount = 0
        this.emit('_connected', {})
      }

      this.ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)
          const type = data.type || data.event || '_message'
          this.emit(type, data)
          this.emit('_message', data) // catch-all
        } catch {
          this.emit('_message', { raw: event.data })
        }
      }

      this.ws.onclose = () => {
        this.emit('_disconnected', {})
        if (!this.intentionalClose && this.retryCount < this.maxRetries) {
          const delay = Math.min(this.baseDelay * Math.pow(2, this.retryCount), 30000)
          this.retryCount++
          this.reconnectTimer = setTimeout(() => this._connect(), delay)
        }
      }

      this.ws.onerror = () => {
        this.ws?.close()
      }
    } catch (e) {
      console.error('[WSManager] Connection error:', e)
    }
  }

  on(event: string, handler: EventHandler) {
    if (!this.handlers.has(event)) {
      this.handlers.set(event, new Set())
    }
    this.handlers.get(event)!.add(handler)
    return () => this.off(event, handler)
  }

  off(event: string, handler: EventHandler) {
    this.handlers.get(event)?.delete(handler)
  }

  private emit(event: string, data: any) {
    this.handlers.get(event)?.forEach((h) => {
      try { h(data) } catch (e) { console.error('[WSManager] Handler error:', e) }
    })
  }

  send(data: any) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(typeof data === 'string' ? data : JSON.stringify(data))
    }
  }

  disconnect() {
    this.intentionalClose = true
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer)
    this.ws?.close()
    this.ws = null
  }

  get connected() {
    return this.ws?.readyState === WebSocket.OPEN
  }
}

// Singleton instance
export const wsManager = new WSManager()
export type { WSManager, EventHandler }
