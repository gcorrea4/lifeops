// Backend datetimes are naive local strings. Formatting never changes payload values.
export const weekdays = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
export function formatDate(value: string | null | undefined): string {
  if (!value) return 'No deadline'
  const [year, month, day] = value.split('-')
  return `${day}/${month}/${year}`
}
export function formatDatetime(value: string): string {
  const [date, time = ''] = value.split('T')
  return `${formatDate(date)} · ${time.slice(0, 5)}`
}
export function formatSlot(slot: { start_datetime: string; end_datetime: string }): string {
  return `${formatDatetime(slot.start_datetime)} – ${slot.end_datetime.slice(11, 16)}`
}
