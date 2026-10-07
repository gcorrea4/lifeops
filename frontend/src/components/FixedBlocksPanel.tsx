import { useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { api, errorMessage } from '../api/client'
import type { FixedBlock, FixedBlockCreate } from '../api/types'
import { formatDate, weekdays } from '../utils/format'

interface Props {
  blocks: FixedBlock[]; loading: boolean; error: string
  onRefresh: () => Promise<void>; onCreated: (block: FixedBlock) => void
}
export default function FixedBlocksPanel({ blocks, loading, error, onRefresh, onCreated }: Props) {
  const [title, setTitle] = useState('')
  const [recurrence, setRecurrence] = useState<'weekly' | 'once'>('weekly')
  const [weekday, setWeekday] = useState(0)
  const [date, setDate] = useState('')
  const [start, setStart] = useState('10:00')
  const [end, setEnd] = useState('12:00')
  const [saving, setSaving] = useState(false)
  const [formError, setFormError] = useState('')
  const [success, setSuccess] = useState('')
  const submitting = useRef(false)
  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (submitting.current) return
    setFormError(''); setSuccess('')
    if (start === end) { setFormError('Start and end times must differ.'); return }
    submitting.current = true; setSaving(true)
    const common = { title: title.trim(), start_time: start, end_time: end }
    const payload: FixedBlockCreate = recurrence === 'weekly'
      ? { ...common, recurrence_type: 'weekly', weekday }
      : { ...common, recurrence_type: 'once', date }
    try {
      const block = await api.createBlock(payload)
      onCreated(block); setTitle('')
      setSuccess(block.spans_next_day ? 'Commitment created. Ends next day.' : 'Commitment created.')
    } catch (error) { setFormError(errorMessage(error)) }
    finally { submitting.current = false; setSaving(false) }
  }
  return (
    <section className="panel" aria-labelledby="blocks-title">
      <div className="section-heading"><h2 id="blocks-title">Fixed commitments</h2>
        <button type="button" className="quiet" disabled={loading} onClick={() => void onRefresh()}>
          {loading ? 'Loading…' : 'Refresh commitments'}
        </button>
      </div>
      {error && <p className="error" role="alert">{error}</p>}
      {!loading && !error && blocks.length === 0 && <p className="muted">Add commitments to reserve unavailable time.</p>}
      <ul className="record-list">
        {blocks.map((block) => <li key={block.id}><div>
          <strong>{block.title}</strong><div className="record-meta">
            {block.recurrence_type === 'weekly' ? 'Every ' + weekdays[block.weekday ?? 0] : formatDate(block.date)}
            {' · '}{block.start_time.slice(0, 5)}–{block.end_time.slice(0, 5)}
          </div>{block.spans_next_day && <span className="badge">Ends next day</span>}
        </div></li>)}
      </ul>
      <form onSubmit={(event) => void create(event)} className="create-form">
        <h3>Create a commitment</h3>
        <label htmlFor="block-title">Title</label>
        <input id="block-title" required value={title} onChange={(event) => setTitle(event.target.value)} />
        <div className="form-row">
          <div><label htmlFor="block-recurrence">Recurrence</label>
            <select id="block-recurrence" value={recurrence}
              onChange={(event) => setRecurrence(event.target.value as 'weekly' | 'once')}>
              <option value="weekly">Weekly</option><option value="once">Once</option>
            </select></div>
          <div>{recurrence === 'weekly' ? <>
            <label htmlFor="block-weekday">Weekday</label>
            <select id="block-weekday" value={weekday} onChange={(event) => setWeekday(Number(event.target.value))}>
              {weekdays.map((day, index) => <option key={day} value={index}>{day}</option>)}
            </select></> : <>
            <label htmlFor="block-date">Date</label>
            <input id="block-date" required type="date" value={date} onChange={(event) => setDate(event.target.value)} />
          </>}</div>
        </div>
        <div className="form-row">
          <div><label htmlFor="block-start">Start time</label>
            <input id="block-start" required type="time" value={start} onChange={(event) => setStart(event.target.value)} /></div>
          <div><label htmlFor="block-end">End time</label>
            <input id="block-end" required type="time" value={end} onChange={(event) => setEnd(event.target.value)} /></div>
        </div>
        {end < start && <p className="muted">This commitment ends next day.</p>}
        {formError && <p className="error" role="alert">{formError}</p>}
        <p className="success" role="status">{success}</p>
        <button type="submit" disabled={saving || !title.trim()}>{saving ? 'Creating…' : 'Create commitment'}</button>
      </form>
    </section>
  )
}
