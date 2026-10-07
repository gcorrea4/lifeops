import type {
  Task, TaskCreate, FixedBlock, FixedBlockCreate, RecommendRequest,
  RecommendResponse, DecisionRequest, DecisionResponse, BookRequest, ScheduledSlot,
} from './types'

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

async function request<T>(path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  const response = await fetch('/api/v1' + path, {
    method: body === undefined ? 'GET' : 'POST',
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
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

export function errorMessage(error: unknown): string {
  return error instanceof ApiError ? `HTTP ${error.status}: ${error.message}`
    : 'Connection interrupted. Refresh the lists to check the outcome before submitting again.'
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
