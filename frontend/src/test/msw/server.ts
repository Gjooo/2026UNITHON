import { setupServer } from 'msw/node'
import { createFakeMvpApi } from './handlers'

export const server = setupServer(...createFakeMvpApi())
