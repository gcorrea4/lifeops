import { useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { api, errorMessage } from '../api/client'
import type { Priority, Task } from '../api/types'
import { formatDate } from '../utils/format'

interface Props {
  tasks: Task[]; loading: boolean; error: string
  onRefresh: () => Promise<void>; onCreated: (task: Task) => void; onPlan: (id: number) => void
}
export default function TasksPanel({ tasks, loading, error, onRefresh, onCreated, onPlan }: Props) {
  const [title, setTitle] = useState('')
  const [duration, setDuration] = useState('60')
  const [priority, setPriority] = useState<Priority>('medium')
  const [deadline, setDeadline] = useState('')
  const [saving, setSaving] = useState(false)
  const [formError, setFormError] = useState('')
  const [success, setSuccess] = useState('')
  const submitting = useRef(false)
  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (submitting.current) return
    submitting.current = true
    setSaving(true); setFormError(''); setSuccess('')
    try {
      const task = await api.createTask({ title: title.trim(), duration_minutes: Number(duration),
        priority, deadline: deadline || null })
      onCreated(task); setTitle(''); setDeadline('')
      setSuccess('Task created.')
    } catch (error) { setFormError(errorMessage(error)) }
    finally { submitting.current = false; setSaving(false) }
  }
  return (
    <section className="panel" aria-labelledby="tasks-title">
      <div className="section-heading"><h2 id="tasks-title">Tasks</h2>
        <button type="button" className="quiet" disabled={loading} onClick={() => void onRefresh()}>
          {loading ? 'Loading…' : 'Refresh tasks'}
        </button>
      </div>
      {error && <p className="error" role="alert">{error}</p>}
      {!loading && !error && tasks.length === 0 && <p className="muted">Create your first task below.</p>}
      <ul className="record-list">
        {tasks.map((task) => <li key={task.id}>
          <div><strong>{task.title}</strong><div className="record-meta">
            {task.duration_minutes} min · {task.priority} priority · {formatDate(task.deadline)}
          </div><span className={'badge status-' + task.status}>{task.status}</span></div>
          {task.status === 'pending' && <button type="button" onClick={() => onPlan(task.id)}>Plan</button>}
        </li>)}
      </ul>
      <form onSubmit={(event) => void create(event)} className="create-form">
        <h3>Create a task</h3>
        <label htmlFor="task-title">Title</label>
        <input id="task-title" required value={title} onChange={(event) => setTitle(event.target.value)} />
        <div className="form-row">
          <div><label htmlFor="task-duration">Duration (minutes)</label>
            <input id="task-duration" type="number" min="1" step="1" required value={duration}
              onChange={(event) => setDuration(event.target.value)} /></div>
          <div><label htmlFor="task-priority">Priority</label>
            <select id="task-priority" value={priority} onChange={(event) => setPriority(event.target.value as Priority)}>
              <option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option>
            </select></div>
        </div>
        <label htmlFor="task-deadline">Deadline (optional)</label>
        <input id="task-deadline" type="date" value={deadline} onChange={(event) => setDeadline(event.target.value)} />
        {formError && <p className="error" role="alert">{formError}</p>}
        <p className="success" role="status">{success}</p>
        <button type="submit" disabled={saving || !title.trim()}>{saving ? 'Creating…' : 'Create task'}</button>
      </form>
    </section>
  )
}
