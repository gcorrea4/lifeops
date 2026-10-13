import { createContext, useContext } from 'react'

export type Theme = 'light' | 'dark'
export const THEME_STORAGE_KEY = 'lifeops-theme'

export interface ThemeState { theme: Theme; toggleTheme: () => void }

export const ThemeContext = createContext<ThemeState | null>(null)

export function useTheme(): ThemeState {
  const value = useContext(ThemeContext)
  if (!value) throw new Error('useTheme must be used inside ThemeProvider')
  return value
}
