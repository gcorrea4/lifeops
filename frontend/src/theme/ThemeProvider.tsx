import { useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { THEME_STORAGE_KEY, ThemeContext } from './context'
import type { Theme } from './context'

const DARK_QUERY = '(prefers-color-scheme: dark)'

// Display preference only; the app works the same if storage is unavailable.
function storedTheme(): Theme | null {
  try {
    const stored = localStorage.getItem(THEME_STORAGE_KEY)
    if (stored === 'light' || stored === 'dark') return stored
  } catch { /* storage unavailable */ }
  return null
}

export default function ThemeProvider({ children }: { children: ReactNode }) {
  const [manual, setManual] = useState<Theme | null>(storedTheme)
  const [systemDark, setSystemDark] = useState(() => window.matchMedia(DARK_QUERY).matches)
  const theme: Theme = manual ?? (systemDark ? 'dark' : 'light')

  // Follow the system preference live until the user makes a manual choice.
  useEffect(() => {
    const query = window.matchMedia(DARK_QUERY)
    const onChange = (event: MediaQueryListEvent) => setSystemDark(event.matches)
    query.addEventListener('change', onChange)
    return () => query.removeEventListener('change', onChange)
  }, [])
  useEffect(() => { document.documentElement.dataset.theme = theme }, [theme])

  const value = useMemo(() => ({
    theme,
    toggleTheme: () => {
      const next: Theme = theme === 'dark' ? 'light' : 'dark'
      setManual(next)
      try { localStorage.setItem(THEME_STORAGE_KEY, next) } catch { /* ignore */ }
    },
  }), [theme])
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
}
