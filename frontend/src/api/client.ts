import type {
  Task, TaskCreate, FixedBlock, FixedBlockCreate, RecommendRequest,
  RecommendResponse, DecisionRequest, DecisionResponse, BookRequest, ScheduledSlot,
} from './types'
import type { Messages } from '../i18n/messages'

export class ApiError extends Error {
  readonly status: number
  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

function detailMessage(detail: unknown): string {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail.map((entry: { loc?: unknown[]; msg?: string }) =>
      [entry.loc?.filter((part) => part !== 'body').join('.'), entry.msg]
        .filter(Boolean).join(': ')).join('; ')
  }
  return 'The request could not be completed.'
}

// Anonymous visitor identifier: keeps each browser's data separate on the public demo (it is not a login).
const SESSION_KEY = 'lifeops-session'
const SESSION_FORMAT = /^[A-Za-z0-9_-]{16,64}$/
let memorySession = ''

function newSessionId(): string {
  return typeof crypto.randomUUID === 'function'
    ? crypto.randomUUID()
    : Array.from(crypto.getRandomValues(new Uint8Array(16)), (byte) => byte.toString(16).padStart(2, '0')).join('')
}

function sessionId(): string {
  try {
    const stored = localStorage.getItem(SESSION_KEY)
    if (stored && SESSION_FORMAT.test(stored)) return stored
    const created = newSessionId()
    localStorage.setItem(SESSION_KEY, created)
    return created
  } catch {
    // Storage unavailable: keep one identifier for this page load only.
    if (!memorySession) memorySession = newSessionId()
    return memorySession
  }
}

async function request<T>(path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  const headers: Record<string, string> = { 'X-Session-Id': sessionId() }
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  const response = await fetch('/api/v1' + path, {
    method: body === undefined ? 'GET' : 'POST',
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
    signal,
  })
  if (!response.ok) {
    let message = 'The request could not be completed.'
    try {
      const data = await response.json() as { detail?: unknown }
      message = detailMessage(data.detail)
    } catch { /* Non-JSON server error: keep the safe default message. */ }
    throw new ApiError(response.status, message)
  }
  return response.json() as Promise<T>
}

// Display text only. Known backend details are translated; unknown ones are shown as received.
// Request-validation errors arrive as "field: Value error, <detail>" (several joined by "; "), so each
// part is matched by exact text or by ending with a known detail; the technical prefix is then dropped.
function translateDetail(message: string, known: Record<string, string>): string {
  return message.split('; ').map((part) => {
    const exact = known[part]
    if (exact) return exact
    const suffix = Object.keys(known).find((key) => part.endsWith(': ' + key) || part.endsWith(', ' + key))
    return suffix ? known[suffix] : part
  }).join('; ')
}

export function errorMessage(error: unknown, t: Pick<Messages, 'connectionError' | 'backendErrors'>): string {
  return error instanceof ApiError
    ? `HTTP ${error.status}: ${translateDetail(error.message, t.backendErrors)}`
    : t.connectionError
}

export const api = {
  tasks: (signal?: AbortSignal) => request<Task[]>('/tasks/', undefined, signal),
  createTask: (body: TaskCreate) => request<Task>('/tasks/', body),
  blocks: (signal?: AbortSignal) => request<FixedBlock[]>('/blocks/', undefined, signal),
  createBlock: (body: FixedBlockCreate) => request<FixedBlock>('/blocks/', body),
  recommend: (body: RecommendRequest) => request<RecommendResponse>('/planner/recommend', body),
  decision: (body: DecisionRequest) => request<DecisionResponse>('/planner/decision', body),
  book: (body: BookRequest) => request<ScheduledSlot>('/engine/book', body),
}
