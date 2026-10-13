import { useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { api, errorMessage } from '../api/client'
import type { FixedBlock, FixedBlockCreate } from '../api/types'
import { useI18n } from '../i18n/context'
import { formatDate } from '../utils/format'

interface Props {
  blocks: FixedBlock[]; loading: boolean; error: string
  onRefresh: () => Promise<void>; onCreated: (block: FixedBlock) => void
}
export default function FixedBlocksPanel({ blocks, loading, error, onRefresh, onCreated }: Props) {
  const { t } = useI18n()
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
    if (start === end) { setFormError(t.timesDiffer); return }
    submitting.current = true; setSaving(true)
    const common = { title: title.trim(), start_time: start, end_time: end }
    const payload: FixedBlockCreate = recurrence === 'weekly'
      ? { ...common, recurrence_type: 'weekly', weekday }
      : { ...common, recurrence_type: 'once', date }
    try {
      const block = await api.createBlock(payload)
      onCreated(block); setTitle('')
      setSuccess(block.spans_next_day ? t.commitmentCreatedNextDay : t.commitmentCreated)
    } catch (error) { setFormError(errorMessage(error, t)) }
    finally { submitting.current = false; setSaving(false) }
  }
  return (
    <section id="commitments" className="panel" aria-labelledby="blocks-title">
      <div className="section-heading"><h2 id="blocks-title">{t.commitments}</h2>
        <button type="button" className="quiet" disabled={loading} onClick={() => void onRefresh()}>
          {loading ? t.loading : t.refreshCommitments}
        </button>
      </div>
      {error && <p className="error" role="alert">{error}</p>}
      {!loading && !error && blocks.length === 0 && <p className="muted">{t.commitmentsEmpty}</p>}
      <ul className="record-list">
        {blocks.map((block) => <li key={block.id}><div>
          <strong>{block.title}</strong><div className="record-meta">
            {block.recurrence_type === 'weekly' ? t.every(t.weekdays[block.weekday ?? 0]) : formatDate(block.date)}
            {' · '}{block.start_time.slice(0, 5)}–{block.end_time.slice(0, 5)}
          </div>{block.spans_next_day && <span className="badge">{t.endsNextDay}</span>}
        </div></li>)}
      </ul>
      <form onSubmit={(event) => void create(event)} className="create-form">
        <h3>{t.createCommitmentHeading}</h3>
        <label htmlFor="block-title">{t.title}</label>
        <input id="block-title" required value={title} onChange={(event) => setTitle(event.target.value)} />
        <div className="form-row">
          <div><label htmlFor="block-recurrence">{t.recurrence}</label>
            <select id="block-recurrence" value={recurrence}
              onChange={(event) => setRecurrence(event.target.value as 'weekly' | 'once')}>
              <option value="weekly">{t.weekly}</option><option value="once">{t.once}</option>
            </select></div>
          <div>{recurrence === 'weekly' ? <>
            <label htmlFor="block-weekday">{t.weekday}</label>
            <select id="block-weekday" value={weekday} onChange={(event) => setWeekday(Number(event.target.value))}>
              {t.weekdays.map((day, index) => <option key={index} value={index}>{day}</option>)}
            </select></> : <>
            <label htmlFor="block-date">{t.date}</label>
            <input id="block-date" required type="date" value={date} onChange={(event) => setDate(event.target.value)} />
          </>}</div>
        </div>
        <div className="form-row">
          <div><label htmlFor="block-start">{t.startTime}</label>
            <input id="block-start" required type="time" value={start} onChange={(event) => setStart(event.target.value)} /></div>
          <div><label htmlFor="block-end">{t.endTime}</label>
            <input id="block-end" required type="time" value={end} onChange={(event) => setEnd(event.target.value)} /></div>
        </div>
        {end < start && <p className="muted">{t.endsNextDayHint}</p>}
        {formError && <p className="error" role="alert">{formError}</p>}
        <p className="success" role="status">{success}</p>
        <button type="submit" disabled={saving || !title.trim()}>{saving ? t.creating : t.createCommitment}</button>
      </form>
    </section>
  )
}
