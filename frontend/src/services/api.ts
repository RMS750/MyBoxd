const LOCAL_BASE = `${window.location.protocol}//${window.location.hostname}:8000/api`
const DEFAULT_BASE = import.meta.env.PROD ? '/api' : LOCAL_BASE
const BASE = (import.meta.env.VITE_API_URL || DEFAULT_BASE).replace(/\/$/, '')
let csrfToken = ''

export function setCsrfToken(token?: string | null) { csrfToken = token || '' }
export function getApiBase() { return BASE }

export class ApiError extends Error {
  status: number
  code?: string
  constructor(message: string, status: number, code?: string) { super(message); this.status = status; this.code = code }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method || 'GET').toUpperCase()
  const headers = new Headers(init.headers)
  if (!['GET', 'HEAD', 'OPTIONS'].includes(method) && csrfToken) headers.set('X-CSRF-Token', csrfToken)
  let res: Response
  try {
    res = await fetch(`${BASE}${path}`, { ...init, headers, credentials: 'include' })
  } catch (error) {
    if ((error as Error).name === 'AbortError') throw error
    throw new ApiError(`Cannot reach the MyBoxd API at ${BASE}. Make sure MyBoxd is running, then refresh the page.`, 0)
  }
  if (!res.ok) {
    let message = `Request failed (${res.status})`
    let code: string | undefined
    try {
      const body = await res.json()
      message = body.detail || body.error?.message || body.message || message
      code = body.code || body.error?.code
    } catch { /* keep safe fallback */ }
    if (res.status === 401 && path !== '/auth/me') window.dispatchEvent(new CustomEvent('myboxd:session-expired'))
    throw new ApiError(message, res.status, code)
  }
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

export const api = {
  get: <T>(path: string, signal?: AbortSignal) => request<T>(path, { signal }),
  post: <T>(path: string, body?: unknown) => request<T>(path, {
    method: 'POST',
    headers: body instanceof FormData ? undefined : { 'Content-Type': 'application/json' },
    body: body instanceof FormData ? body : body === undefined ? undefined : JSON.stringify(body),
  }),
  put: <T>(path: string, body: unknown) => request<T>(path, {
    method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  }),
  del: <T>(path: string) => request<T>(path, { method: 'DELETE' }),
  upload: <T>(path: string, files: File[], fields?: Record<string, string>) => {
    const form = new FormData()
    files.forEach((file) => form.append('files', file))
    Object.entries(fields || {}).forEach(([key, value]) => form.append(key, value))
    return request<T>(path, { method: 'POST', body: form })
  },
}
