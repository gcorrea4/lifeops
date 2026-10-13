import { useEffect, useState } from 'react'

// Highlights the nav link of the section currently in view (presentation only).
// Sections can sit side by side, so the current one is kept while it stays in view;
// clicking a nav link sets it directly via the returned setter.
export function useActiveSection(ids: string[]): [string, (id: string) => void] {
  const [active, setActive] = useState(ids[0])
  const key = ids.join('|')
  useEffect(() => {
    const order = key.split('|')
    const visible = new Set<string>()
    const observer = new IntersectionObserver((entries) => {
      for (const entry of entries) {
        if (entry.isIntersecting) visible.add(entry.target.id)
        else visible.delete(entry.target.id)
      }
      setActive((current) => {
        if (visible.has(current)) return current
        const next = order.find((id) => visible.has(id))
        if (next) return next
        return window.scrollY < 100 ? order[0] : current // back at the hero: first section
      })
    }, { rootMargin: '-20% 0px -55% 0px' })
    order.forEach((id) => {
      const element = document.getElementById(id)
      if (element) observer.observe(element)
    })
    return () => observer.disconnect()
  }, [key])
  return [active, setActive]
}
