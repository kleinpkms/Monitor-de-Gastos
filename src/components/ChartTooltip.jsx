import { currencyFormatter } from '../theme.js'

export default function ChartTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  const point = payload[0]

  return (
    <div className="chart-tooltip">
      <strong>{label}</strong>
      <div>{currencyFormatter.format(point.value)}</div>
      {point.payload.count !== undefined && <div className="muted">{point.payload.count} lançamento(s)</div>}
    </div>
  )
}
