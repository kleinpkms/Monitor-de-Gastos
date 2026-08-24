import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import ChartTooltip from './ChartTooltip.jsx'
import { COLORS, compactCurrencyFormatter, currencyFormatter } from '../theme.js'

const GROUP_LABELS = { day: 'dia', week: 'semana', month: 'mês' }

export default function TrendChart({ summary }) {
  const data = summary?.buckets ?? []
  const label = GROUP_LABELS[summary?.group_by] ?? 'período'

  return (
    <div className="card chart-card">
      <div className="chart-header">
        <h2>Evolução por {label}</h2>
        {summary && <span className="chart-total">Total: {currencyFormatter.format(summary.total)}</span>}
      </div>
      {data.length === 0 ? (
        <p className="empty-state">Nenhum gasto no período selecionado.</p>
      ) : (
        <ResponsiveContainer width="100%" height={320}>
          <AreaChart data={data} margin={{ top: 8, right: 16, left: 8, bottom: 0 }}>
            <defs>
              <linearGradient id="trendFill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={COLORS.accent} stopOpacity={0.35} />
                <stop offset="100%" stopColor={COLORS.accent} stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid vertical={false} stroke={COLORS.grid} />
            <XAxis
              dataKey="key"
              tick={{ fill: COLORS.muted, fontSize: 12 }}
              axisLine={{ stroke: COLORS.grid }}
              tickLine={false}
            />
            <YAxis
              tick={{ fill: COLORS.muted, fontSize: 12 }}
              axisLine={false}
              tickLine={false}
              tickFormatter={(value) => compactCurrencyFormatter.format(value)}
              width={80}
            />
            <Tooltip content={<ChartTooltip />} cursor={{ stroke: COLORS.grid }} />
            <Area
              type="monotone"
              dataKey="total"
              stroke={COLORS.accent}
              strokeWidth={2}
              fill="url(#trendFill)"
              dot={{ r: 3, fill: COLORS.accent, strokeWidth: 0 }}
              activeDot={{ r: 5 }}
            />
          </AreaChart>
        </ResponsiveContainer>
      )}
    </div>
  )
}
