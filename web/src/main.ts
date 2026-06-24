// App entry — register all components
import './components/mf-app'
import { initAnalytics } from './analytics'

initAnalytics(import.meta.env.PROD)
