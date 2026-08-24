const CURRENCY_FORMATTER = new Intl.NumberFormat('pt-BR', {
  style: 'currency',
  currency: 'BRL',
})
const DATE_FORMATTER = new Intl.DateTimeFormat('pt-BR', { timeZone: 'UTC' })

export default function ExpenseList({ expenses, total, page, limit, onPageChange, onDelete }) {
  const totalPages = Math.max(1, Math.ceil(total / limit))

  return (
    <div className="card">
      <h2>Lançamentos</h2>
      <div className="table-wrapper">
        <table>
          <thead>
            <tr>
              <th>Data</th>
              <th>Descrição</th>
              <th>Categoria</th>
              <th>Tags</th>
              <th className="align-right">Valor</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {expenses.map((expense) => (
              <tr key={expense.id}>
                <td>{DATE_FORMATTER.format(new Date(expense.date))}</td>
                <td>{expense.description}</td>
                <td>
                  <span className="badge">{expense.category}</span>
                </td>
                <td className="muted">{expense.tags.join(', ')}</td>
                <td className="align-right">{CURRENCY_FORMATTER.format(expense.amount)}</td>
                <td>
                  <button type="button" className="ghost danger" onClick={() => onDelete(expense.id)}>
                    Excluir
                  </button>
                </td>
              </tr>
            ))}
            {expenses.length === 0 && (
              <tr>
                <td colSpan={6} className="empty-state">
                  Nenhum gasto encontrado.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      <div className="pagination">
        <span className="muted">
          Página {page} de {totalPages} · {total} lançamento(s)
        </span>
        <div>
          <button type="button" disabled={page <= 1} onClick={() => onPageChange(page - 1)}>
            Anterior
          </button>
          <button type="button" disabled={page >= totalPages} onClick={() => onPageChange(page + 1)}>
            Próxima
          </button>
        </div>
      </div>
    </div>
  )
}
