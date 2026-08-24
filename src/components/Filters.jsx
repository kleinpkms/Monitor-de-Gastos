const GROUP_BY_OPTIONS = [
  { value: 'day', label: 'Dia' },
  { value: 'week', label: 'Semana' },
  { value: 'month', label: 'Mês' },
]

export default function Filters({ filters, categories, onChange }) {
  function update(field, value) {
    onChange({ ...filters, [field]: value })
  }

  return (
    <div className="card filters">
      <label>
        Categoria
        <select value={filters.category} onChange={(e) => update('category', e.target.value)}>
          <option value="">Todas</option>
          {categories.map((category) => (
            <option key={category} value={category}>
              {category}
            </option>
          ))}
        </select>
      </label>
      <label>
        De
        <input
          type="date"
          value={filters.startDate}
          onChange={(e) => update('startDate', e.target.value)}
        />
      </label>
      <label>
        Até
        <input
          type="date"
          value={filters.endDate}
          onChange={(e) => update('endDate', e.target.value)}
        />
      </label>
      <label>
        Evolução por
        <select value={filters.groupBy} onChange={(e) => update('groupBy', e.target.value)}>
          {GROUP_BY_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </label>
      <button
        type="button"
        className="ghost"
        onClick={() => onChange({ category: '', startDate: '', endDate: '', groupBy: filters.groupBy })}
      >
        Limpar filtros
      </button>
    </div>
  )
}
