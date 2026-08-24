import { useCallback, useEffect, useMemo, useState } from 'react'
import Filters from './components/Filters.jsx'
import ExpenseForm from './components/ExpenseForm.jsx'
import ImportInvoice from './components/ImportInvoice.jsx'
import TrendChart from './components/TrendChart.jsx'
import CategoryChart from './components/CategoryChart.jsx'
import ExpenseList from './components/ExpenseList.jsx'
import StatCard from './components/StatCard.jsx'
import { createExpense, deleteExpense, getSummary, listCategories, listExpenses } from './services/api.js'
import { currencyFormatter } from './theme.js'

const LIMIT = 10

export default function App() {
  const [filters, setFilters] = useState({
    category: '',
    startDate: '',
    endDate: '',
    groupBy: 'month',
  })
  const [page, setPage] = useState(1)
  const [categories, setCategories] = useState([])
  const [expensesData, setExpensesData] = useState({ items: [], total: 0 })
  const [summaryByCategory, setSummaryByCategory] = useState(null)
  const [summaryByTime, setSummaryByTime] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const baseParams = {
    category: filters.category || undefined,
    start_date: filters.startDate || undefined,
    end_date: filters.endDate || undefined,
  }

  const listParams = { ...baseParams, page, limit: LIMIT }
  const categorySummaryParams = { ...baseParams, group_by: 'category' }
  const timeSummaryParams = { ...baseParams, group_by: filters.groupBy }

  const refresh = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [expensesResult, categorySummary, timeSummary, categoriesResult] = await Promise.all([
        listExpenses(listParams),
        getSummary(categorySummaryParams),
        getSummary(timeSummaryParams),
        listCategories(),
      ])
      setExpensesData(expensesResult)
      setSummaryByCategory(categorySummary)
      setSummaryByTime(timeSummary)
      setCategories(categoriesResult)
    } catch {
      setError('Não foi possível carregar os dados. Verifique se a API está no ar.')
    } finally {
      setLoading(false)
    }
  }, [JSON.stringify(listParams), JSON.stringify(categorySummaryParams), JSON.stringify(timeSummaryParams)])

  useEffect(() => {
    refresh()
  }, [refresh])

  useEffect(() => {
    setPage(1)
  }, [filters.category, filters.startDate, filters.endDate])

  const kpis = useMemo(() => {
    const buckets = summaryByCategory?.buckets ?? []
    const total = summaryByCategory?.total ?? 0
    const count = buckets.reduce((acc, bucket) => acc + bucket.count, 0)
    const average = count > 0 ? total / count : 0
    const top = buckets.reduce((best, bucket) => (bucket.total > (best?.total ?? -Infinity) ? bucket : best), null)
    return { total, count, average, top }
  }, [summaryByCategory])

  async function handleCreate(payload) {
    await createExpense(payload)
    await refresh()
  }

  async function handleDelete(id) {
    await deleteExpense(id)
    await refresh()
  }

  return (
    <div className="app-shell">
      <header>
        <div className="header-title">
          <span className={`status-dot ${error ? 'status-dot--error' : 'status-dot--ok'}`} />
          <h1>Monitor de Gastos</h1>
        </div>
        <p className="muted">Acompanhe, categorize e analise seus gastos.</p>
      </header>

      {error && <div className="alert">{error}</div>}

      <div className="stat-grid">
        <StatCard label="Total no período" value={currencyFormatter.format(kpis.total)} />
        <StatCard label="Ticket médio" value={currencyFormatter.format(kpis.average)} />
        <StatCard
          label="Maior categoria"
          value={kpis.top ? kpis.top.key : '—'}
          hint={kpis.top ? currencyFormatter.format(kpis.top.total) : undefined}
        />
        <StatCard label="Lançamentos" value={String(kpis.count)} />
      </div>

      <Filters filters={filters} categories={categories} onChange={setFilters} />

      <div className="charts-grid">
        <TrendChart summary={summaryByTime} />
        <CategoryChart summary={summaryByCategory} />
      </div>

      <ImportInvoice categories={categories} onImported={refresh} />

      <div className="layout-grid">
        <ExpenseForm categories={categories} onCreate={handleCreate} />
        <ExpenseList
          expenses={expensesData.items}
          total={expensesData.total}
          page={page}
          limit={LIMIT}
          onPageChange={setPage}
          onDelete={handleDelete}
        />
      </div>

      {loading && <div className="loading-indicator">Carregando…</div>}
    </div>
  )
}
