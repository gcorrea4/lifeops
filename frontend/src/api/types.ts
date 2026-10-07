export type Priority = 'low' | 'medium' | 'high'
export type TaskStatus = 'pending' | 'scheduled' | 'done'
export type UserAction = 'APPROVED' | 'MODIFIED' | 'REJECTED'
export interface TaskCreate {
  title: string
  duration_minutes: number
  priority: Priority
  deadline?: string | null
}
export interface Task extends TaskCreate {
  id: number
  user_id: number
  status: TaskStatus
  deadline: string | null
  created_at: string
}
type BlockBase = { title: string; start_time: string; end_time: string }
export type FixedBlockCreate = BlockBase & (
  | { recurrence_type: 'weekly'; weekday: number }
  | { recurrence_type: 'once'; date: string }
)
export interface FixedBlock extends BlockBase {
  id: number
  user_id: number
  recurrence_type: 'weekly' | 'once'
  weekday: number | null
  date: string | null
  spans_next_day: boolean
  created_at: string
}
export interface RecommendedSlot {
  start_datetime: string
  end_datetime: string
}
export interface SlotSuggestion extends RecommendedSlot { date: string }
export interface RecommendRequest { task_id: number; from_date?: string }
export interface RecommendResponse {
  recommendation_id: number
  task_id: number
  recommended_slot: RecommendedSlot
  explanation: string
  reason_codes: string[]
  fallback_used: boolean
  candidate_slots: SlotSuggestion[]
}
export type DecisionRequest =
  | { recommendation_id: number; action: 'APPROVED' | 'REJECTED' }
  | { recommendation_id: number; action: 'MODIFIED'; chosen_start: string; chosen_end: string }
export interface DecisionResponse {
  recommendation_id: number
  action: UserAction
  final_start: string | null
  final_end: string | null
  message: string
}
export interface BookRequest { task_id: number; start_datetime: string }
export interface ScheduledSlot extends RecommendedSlot {
  id: number
  task_id: number
  user_id: number
  created_at: string
}
