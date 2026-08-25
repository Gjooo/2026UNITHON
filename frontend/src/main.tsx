import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { App } from '@/app/App'
import { AppProviders, createAppQueryClient } from '@/app/AppProviders'

const container = document.getElementById('root')
if (!container) throw new Error('#root element not found')

createRoot(container).render(
  <StrictMode>
    <AppProviders queryClient={createAppQueryClient()}>
      <App />
    </AppProviders>
  </StrictMode>,
)
