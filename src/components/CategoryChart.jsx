import { Bar, BarChart, CartesianGrid, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import ChartTooltip from './ChartTooltip.jsx'
import { COLORS, compactCurrencyFormatter } from '../theme.js'

const MAX_SLOTS = 8

function foldTail(buckets) {
  const sorted = [...buckets].sort((a, b) => b.total - a.total)
  if (sorted.length <= MAX_SLOTS) return sorted

  const head = sorted.slice(0, MAX_SLOTS - 1)
  const tail = sorted.slice(MAX_SLOTS - 1)
  const folded = tail.reduce(
    (acc, bucket) => ({ total: acc.total + bucket.total, count: acc.count + bucket.count }),
    { total: 0, count: 0 },
  )
  return [...head, { key: 'Outras', ...folded }]
}

export default function CategoryChart({ summary }) {
  const data = foldTail(summary?.buckets ?? [])

  return (
    <div className="card chart-card">
      <div className="chart-header">
        <h2>Gastos por categoria</h2>
      </div>
      {data.length === 0 ? (
        <p className="empty-state">Nenhum gasto no período selecionado.</p>
      ) : (
        <ResponsiveContainer width="100%" height={Math.max(220, data.length * 42)}>
          <BarChart data={data} layout="vertical" margin={{ top: 4, right: 40, left: 8, bottom: 4 }}>
            <CartesianGrid horizontal={false} stroke={COLORS.grid} />
            <XAxis
              type="number"
              tick={{ fill: COLORS.muted, fontSize: 12 }}
              axisLine={false}
              tickLine={false}
              tickFormatter={(value) => compactCurrencyFormatter.format(value)}
            />
            <YAxis
              type="category"
              dataKey="key"
              tick={{ fill: COLORS.textSecondary, fontSize: 12 }}
              axisLine={false}
              tickLine={false}
              width={110}
            />
            <Tooltip content={<ChartTooltip />} cursor={{ fill: 'rgba(255,255,255,0.04)' }} />
            <Bar dataKey="total" fill={COLORS.accent} radius={[0, 4, 4, 0]} maxBarSize={22}>
              <LabelList
                dataKey="total"
                position="right"
                formatter={(value) => compactCurrencyFormatter.format(value)}
                fill={COLORS.textSecondary}
                fontSize={12}
              />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      )}
    </div>
  )
}
