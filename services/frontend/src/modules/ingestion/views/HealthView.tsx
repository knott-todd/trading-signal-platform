import { useQuery } from '@tanstack/react-query'
import { clsx } from 'clsx'
import {
  Database, Wifi, WifiOff, Calendar, Clock, Trash2,
  CheckCircle, XCircle, AlertTriangle, Loader2
} from 'lucide-react'
import { api } from '@/lib/api'
import { formatDistanceToNow, format } from 'date-fns'

const STATUS_COLORS: Record<string, string> = {
  healthy:  'border-green/30 bg-green/5',
  degraded: 'border-amber/30 bg-amber/5',
  unhealthy:'border-red/30 bg-red/5',
  offline:  'border-border bg-surface',
  unknown:  'border-border bg-surface',
}
const STATUS_ICON: Record<string, React.ReactNode> = {
  healthy:  <CheckCircle size={14} className="text-green" />,
  degraded: <AlertTriangle size={14} className="text-amber" />,
  unhealthy:<XCircle size={14} className="text-red" />,
  offline:  <XCircle size={14} className="text-red" />,
  unknown:  <Loader2 size={14} className="text-dim animate-spin" />,
}

function StatusTag({ status }: { status: string }) {
  const cls =
    status === 'healthy'  ? 'tag-green' :
    status === 'degraded' ? 'tag-amber' :
    status === 'offline' || status === 'unhealthy' ? 'tag-red' : 'tag-grey'
  return <span className={`tag ${cls}`}>{status.toUpperCase()}</span>
}

function Card({
  icon, title, status, children
}: {
  icon: React.ReactNode
  title: string
  status: string
  children: React.ReactNode
}) {
  return (
    <div className={clsx('rounded-sm border p-4 flex flex-col gap-3', STATUS_COLORS[status] ?? STATUS_COLORS.unknown)}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-text">
          {icon}
          <span className="text-[11px] font-mono uppercase tracking-widest text-dim">{title}</span>
        </div>
        <div className="flex items-center gap-2">
          {STATUS_ICON[status]}
          <StatusTag status={status} />
        </div>
      </div>
      <div className="flex flex-col gap-2">{children}</div>
    </div>
  )
}

function Row({ label, value, highlight }: { label: string; value: React.ReactNode; highlight?: string }) {
  return (
    <div className="flex items-center justify-between">
      <span className="label-xs">{label}</span>
      <span className={clsx('text-[11px] font-mono', highlight ?? 'text-text')}>{value}</span>
    </div>
  )
}

function JobRow({ job }: { job: any }) {
  const nextRun = job.next_run_time ? format(new Date(job.next_run_time), 'HH:mm:ss') : '—'
  return (
    <div className="flex items-center gap-3 py-1 border-t border-border/50 first:border-0">
      <span className="text-[11px] font-mono text-text flex-1">{job.name}</span>
      <span className="label-xs text-right">
        next {nextRun}
      </span>
    </div>
  )
}

export default function HealthView() {
  const { data, isLoading, error, dataUpdatedAt } = useQuery({
    queryKey: ['ingestion-health'],
    queryFn: api.ingestionHealth,
    refetchInterval: 10_000,
  })

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 size={20} className="text-dim animate-spin" />
        <span className="ml-2 text-dim text-xs font-mono">Loading health data...</span>
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-full">
        <XCircle size={16} className="text-red mr-2" />
        <span className="text-red text-xs font-mono">Cannot reach gateway: {String(error)}</span>
      </div>
    )
  }

  const cards = data?.cards ?? []
  const dbCard       = cards.find((c: any) => c.subsystem === 'database')
  const alpacaCard   = cards.find((c: any) => c.subsystem === 'alpaca_connection')
  const streamCard   = cards.find((c: any) => c.subsystem === 'websocket_stream')
  const schedulerCard= cards.find((c: any) => c.subsystem === 'scheduler')
  const jobs: any[]  = schedulerCard?.detail?.jobs ?? []

  const streamDetail = streamCard?.detail ?? {}

  return (
    <div className="flex flex-col h-full overflow-y-auto p-5 gap-5">
      {/* Header */}
      <div className="flex items-center justify-between flex-shrink-0">
        <div>
          <h1 className="text-sm font-mono font-semibold text-bright uppercase tracking-widest">
            Pipeline Health
          </h1>
          <p className="text-dim text-[11px] font-mono mt-0.5">
            Module 01 — Data Ingestion · subsystem status
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="label-xs">Last updated</span>
          <span className="text-[11px] font-mono text-text">
            {dataUpdatedAt ? format(new Date(dataUpdatedAt), 'HH:mm:ss') : '—'}
          </span>
        </div>
      </div>

      {/* Grid */}
      <div className="grid grid-cols-2 gap-3 flex-shrink-0">
        {/* Database */}
        <Card icon={<Database size={14} />} title="Database" status={dbCard?.status ?? 'unknown'}>
          <Row
            label="Connection"
            value={dbCard?.detail?.connected ? 'Connected' : 'Unreachable'}
            highlight={dbCard?.detail?.connected ? 'text-green' : 'text-red'}
          />
        </Card>

        {/* Alpaca */}
        <Card
          icon={<Wifi size={14} />}
          title="Alpaca Connection"
          status={alpacaCard?.status ?? 'unknown'}
        >
          <Row label="Status" value={alpacaCard?.status === 'healthy' ? 'Authenticated' : 'Unreachable'} />
          {alpacaCard?.detail?.last_check && (
            <Row
              label="Last check"
              value={formatDistanceToNow(new Date(alpacaCard.detail.last_check), { addSuffix: true })}
            />
          )}
        </Card>

        {/* WebSocket Stream */}
        <Card
          icon={streamCard?.status === 'healthy' ? <Wifi size={14} /> : <WifiOff size={14} />}
          title="WebSocket Stream"
          status={streamCard?.status ?? 'unknown'}
        >
          <Row
            label="State"
            value={streamDetail.state ?? '—'}
            highlight={
              streamDetail.state === 'connected' ? 'text-green' :
              streamDetail.state === 'disconnected' ? 'text-dim' : 'text-amber'
            }
          />
          <Row label="Subscriptions" value={streamDetail.symbol_count ?? 0} />
          {streamDetail.session_started_at && (
            <Row
              label="Connected since"
              value={formatDistanceToNow(new Date(streamDetail.session_started_at), { addSuffix: true })}
            />
          )}
        </Card>

        {/* Scheduler */}
        <Card icon={<Calendar size={14} />} title="Scheduler" status={schedulerCard?.status ?? 'unknown'}>
          {jobs.length === 0 ? (
            <span className="text-dim text-[11px] font-mono">No jobs registered</span>
          ) : (
            <div className="flex flex-col">
              {jobs.map((job: any) => (
                <JobRow key={job.id} job={job} />
              ))}
            </div>
          )}
        </Card>
      </div>

      {/* Overall status banner */}
      <div className={clsx(
        'flex items-center gap-3 px-4 py-3 rounded-sm border flex-shrink-0',
        data?.overall === 'healthy'
          ? 'border-green/30 bg-green/5 text-green'
          : data?.overall === 'degraded'
          ? 'border-amber/30 bg-amber/5 text-amber'
          : 'border-red/30 bg-red/5 text-red'
      )}>
        {STATUS_ICON[data?.overall ?? 'unknown']}
        <span className="text-xs font-mono font-semibold uppercase tracking-widest">
          Module 01 — {data?.overall?.toUpperCase() ?? 'UNKNOWN'}
        </span>
      </div>
    </div>
  )
}
