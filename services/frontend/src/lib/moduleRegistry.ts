import { lazy, ComponentType } from 'react'

export interface ModuleView {
  id: string
  label: string
  icon: string
  component: ComponentType
  verificationView: boolean
}

export interface ModuleRegistration {
  id: string
  label: string
  version: string
  healthEndpoint: string
  views: ModuleView[]
}

// Lazy-loaded view components
const HealthView    = lazy(() => import('@/modules/ingestion/views/HealthView'))
const CoverageView  = lazy(() => import('@/modules/ingestion/views/CoverageView'))
const BarViewerView = lazy(() => import('@/modules/ingestion/views/BarViewerView'))
const LiveFeedView  = lazy(() => import('@/modules/ingestion/views/LiveFeedView'))

export const MODULE_REGISTRY: ModuleRegistration[] = [
  {
    id: 'ingestion',
    label: 'Data Ingestion',
    version: '0.2.0',
    healthEndpoint: '/api/ingestion/health',
    views: [
      {
        id: 'health',
        label: 'Pipeline Health',
        icon: 'Activity',
        component: HealthView,
        verificationView: true,
      },
      {
        id: 'coverage',
        label: 'Watchlist & Coverage',
        icon: 'LayoutGrid',
        component: CoverageView,
        verificationView: true,
      },
      {
        id: 'barviewer',
        label: 'Bar Viewer',
        icon: 'CandlestickChart',
        component: BarViewerView,
        verificationView: true,
      },
      {
        id: 'livefeed',
        label: 'Live Feed',
        icon: 'Radio',
        component: LiveFeedView,
        verificationView: true,
      },
    ],
  },
  // To add a new module:
  // 1. Import its views here (lazy)
  // 2. Add an entry to this array
  // 3. Add gateway routes under /api/{module_id}/
  // 4. Add health card handling in gateway
  // No other files change.
]
