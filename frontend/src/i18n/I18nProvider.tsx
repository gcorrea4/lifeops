import { useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { I18nContext } from './context'
import { messages } from './messages'
import type { Lang } from './messages'

const STORAGE_KEY = 'lifeops-lang'

// Display preference only; the app works the same if storage is unavailable.
function initialLang(): Lang {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored === 'en' || stored === 'pt') return stored
  } catch { /* storage unavailable */ }
  return navigator.language.toLowerCase().startsWith('pt') ? 'pt' : 'en'
}

export default function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(initialLang)
  useEffect(() => { document.documentElement.lang = lang === 'pt' ? 'pt-BR' : 'en' }, [lang])
  const value = useMemo(() => ({
    lang,
    t: messages[lang],
    setLang: (next: Lang) => {
      setLangState(next)
      try { localStorage.setItem(STORAGE_KEY, next) } catch { /* ignore */ }
    },
  }), [lang])
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>
}
