import { useEffect, useRef, useState } from 'react'
import { api, errorMessage } from '../api/client'
import type { DecisionRequest, DecisionResponse, RecommendResponse, ScheduledSlot, Task, UserAction } from '../api/types'
import { formatSlot, formatDatetime } from '../utils/format'

type PlannerState =
  | { phase: 'idle' }
  | { phase: 'recommending' }
  | { phase: 'review'; recommendation: RecommendResponse }
  | { phase: 'decided'; recommendation: RecommendResponse; decision: DecisionResponse }
  | { phase: 'booked'; recommendation: RecommendResponse; slot: ScheduledSlot }

interface Props {
  tasks: Task[]
  selectedTaskId: number | null
  onSelect: (id: number | null) => void
  onRefreshTasks: () => Promise<void>
}
export default function PlannerPanel({ tasks, selectedTaskId, onSelect, onRefreshTasks }: Props) {
  const [state, setState] = useState<PlannerState>({ phase: 'idle' })
  const [candidateIndex, setCandidateIndex] = useState<number | null>(null)
  const [busy, setBusy] = useState<'decision' | 'booking' | null>(null)
  const [error, setError] = useState('')
  const mounted = useRef(true)
  const submitting = useRef(false)
  useEffect(() => {
    mounted.current = true
    return () => { mounted.current = false }
  }, [])
  const task = tasks.find((item) => item.id === selectedTaskId)
  const pending = tasks.filter((item) => item.status === 'pending')
  const recommendation = 'recommendation' in state ? state.recommendation : null
  const loading = state.phase === 'recommending' || busy !== null

  async function recommend() {
    if (!task || task.status !== 'pending' || submitting.current) return
    submitting.current = true
    setError(''); setCandidateIndex(null); setState({ phase: 'recommending' })
    try {
      const result = await api.recommend({ task_id: task.id })
      if (mounted.current) setState({ phase: 'review', recommendation: result })
    } catch (error) {
      if (mounted.current) { setError(errorMessage(error)); setState({ phase: 'idle' }) }
    } finally { submitting.current = false }
  }

  async function decide(action: UserAction) {
    if (state.phase !== 'review' || submitting.current) return
    const snapshot = state.recommendation
    const candidate = candidateIndex === null ? null : snapshot.candidate_slots[candidateIndex]
    if (action === 'MODIFIED' && !candidate) return
    const payload: DecisionRequest = action === 'MODIFIED' && candidate
      ? { recommendation_id: snapshot.recommendation_id, action: 'MODIFIED',
        chosen_start: candidate.start_datetime, chosen_end: candidate.end_datetime }
      : { recommendation_id: snapshot.recommendation_id, action: action as 'APPROVED' | 'REJECTED' }
    submitting.current = true; setBusy('decision'); setError('')
    try {
      const decision = await api.decision(payload)
      if (mounted.current) setState({ phase: 'decided', recommendation: snapshot, decision })
    } catch (error) {
      if (mounted.current) setError(errorMessage(error))
    } finally {
      submitting.current = false
      if (mounted.current) setBusy(null)
    }
  }

  async function book() {
    if (state.phase !== 'decided' || state.decision.action === 'REJECTED'
        || !state.decision.final_start || submitting.current) return
    const { recommendation: snapshot, decision } = state
    submitting.current = true; setBusy('booking'); setError('')
    try {
      const slot = await api.book({ task_id: snapshot.task_id, start_datetime: decision.final_start! })
      if (mounted.current) setState({ phase: 'booked', recommendation: snapshot, slot })
      // Refresh even if the user selected another task while the booking was in flight.
      await onRefreshTasks()
    } catch (error) {
      if (mounted.current) setError(errorMessage(error))
    } finally {
      submitting.current = false
      if (mounted.current) setBusy(null)
    }
  }

  return (
    <section id="planner" className="panel planner" aria-labelledby="planner-title">
      <div className="section-heading"><div><span className="eyebrow">REVIEW → DECIDE → BOOK</span>
        <h2 id="planner-title">Plan a task</h2></div></div>
      <div className="planner-start">
        <div><label htmlFor="planner-task">Pending task</label>
          <select id="planner-task" value={selectedTaskId ?? ''}
            onChange={(event) => onSelect(event.target.value ? Number(event.target.value) : null)}>
            <option value="">Select a task</option>
            {pending.map((item) => <option key={item.id} value={item.id}>{item.title}</option>)}
            {task && task.status !== 'pending' && <option value={task.id}>{task.title} ({task.status})</option>}
          </select>
        </div>
        <button className="primary" type="button"
          disabled={!task || task.status !== 'pending' || loading}
          onClick={() => void recommend()}>
          {state.phase === 'recommending' ? 'Getting recommendation…'
            : state.phase === 'idle' ? 'Get recommendation' : 'Get new recommendation'}
        </button>
      </div>
      {!pending.length && !task && <p className="muted">Create a pending task to start planning.</p>}
      {state.phase === 'recommending' && <p role="status">Checking valid slots and requesting a recommendation…</p>}
      {error && <p className="error" role="alert">{error}</p>}
      {recommendation && <>
        <div className="recommendation">
          <div className="section-heading"><h3>Recommended slot</h3>
            <span className="muted">Recommendation #{recommendation.recommendation_id}</span></div>
          <p className="slot-heading">{formatSlot(recommendation.recommended_slot)}</p>
          <p>{recommendation.explanation}</p>
          <div className="badges">{recommendation.reason_codes.map((code) =>
            <span className="badge" key={code}>{code}</span>)}</div>
          <p className={recommendation.fallback_used ? 'fallback' : 'muted'}>
            Fallback used: {recommendation.fallback_used ? 'Yes — deterministic candidate selected.' : 'No'}
          </p>
        </div>
        <fieldset className="candidates" disabled={state.phase !== 'review' || loading}>
          <legend>Original candidate slots</legend>
          <p className="muted">Choose a candidate below to modify the recommendation.</p>
          {recommendation.candidate_slots.map((candidate, index) => <label className="candidate" key={index}>
            <input type="radio" name="candidate" value={index} checked={candidateIndex === index}
              onChange={() => setCandidateIndex(index)} />
            <span>{formatSlot(candidate)}</span>
            {candidate.start_datetime === recommendation.recommended_slot.start_datetime
              && candidate.end_datetime === recommendation.recommended_slot.end_datetime
              && <span className="badge">Recommended</span>}
          </label>)}
        </fieldset>
        {state.phase === 'review' && <div className="actions">
          <button type="button" className="primary" disabled={loading} onClick={() => void decide('APPROVED')}>
            Approve recommended slot</button>
          <button type="button" disabled={loading || candidateIndex === null} onClick={() => void decide('MODIFIED')}>
            Modify to selected candidate</button>
          <button type="button" className="quiet" disabled={loading} onClick={() => void decide('REJECTED')}>Reject</button>
          {busy === 'decision' && <span role="status">Recording decision…</span>}
        </div>}
      </>}
      {state.phase === 'decided' && <div className="decision" role="status">
        {state.decision.action === 'REJECTED'
          ? <p>Recommendation rejected. Task is still pending. Nothing was booked.</p>
          : <>
            <p><strong>Decision recorded. Task is still pending.</strong></p>
            {state.decision.final_start && state.decision.final_end && <p>
              Selected slot: {formatSlot({ start_datetime: state.decision.final_start, end_datetime: state.decision.final_end })}
            </p>}
            <p className="muted">Booking is a separate action and rechecks current availability.</p>
            <button className="primary" type="button" disabled={loading || !state.decision.final_start || !state.decision.final_end}
              onClick={() => void book()}>{busy === 'booking' ? 'Booking…' : 'Book selected slot'}</button>
          </>}
      </div>}
      {state.phase === 'booked' && <div className="decision success" role="status">
        <h3>Booking confirmed</h3>
        <p>ScheduledSlot #{state.slot.id} · Task #{state.slot.task_id}</p>
        <p>{formatDatetime(state.slot.start_datetime)} – {state.slot.end_datetime.slice(11, 16)}</p>
        <p>Task is now scheduled.</p>
      </div>}
    </section>
  )
}
