import { useState } from 'react'

const initialState = {
  amount: '',
  description: '',
  date: new Date().toISOString().slice(0, 10),
  category: '',
  tags: '',
}

export default function ExpenseForm({ categories, onCreate }) {
  const [form, setForm] = useState(initialState)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)

  function handleChange(event) {
    const { name, value } = event.target
    setForm((prev) => ({ ...prev, [name]: value }))
  }

  async function handleSubmit(event) {
    event.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      await onCreate({
        amount: Number(form.amount),
        description: form.description.trim(),
        date: form.date,
        category: form.category.trim(),
        tags: form.tags
          .split(',')
          .map((tag) => tag.trim())
          .filter(Boolean),
      })
      setForm(initialState)
    } catch (err) {
      setError(err?.response?.data?.detail ?? 'Não foi possível salvar o gasto.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form className="card expense-form" onSubmit={handleSubmit}>
      <h2>Novo gasto</h2>
      <div className="form-grid">
        <label>
          Valor (R$)
          <input
            type="number"
            name="amount"
            min="0.01"
            step="0.01"
            required
            value={form.amount}
            onChange={handleChange}
          />
        </label>
        <label>
          Data
          <input type="date" name="date" required value={form.date} onChange={handleChange} />
        </label>
        <label className="span-2">
          Descrição
          <input
            type="text"
            name="description"
            required
            maxLength={200}
            value={form.description}
            onChange={handleChange}
          />
        </label>
        <label>
          Categoria
          <input
            type="text"
            name="category"
            required
            list="category-options"
            value={form.category}
            onChange={handleChange}
          />
          <datalist id="category-options">
            {categories.map((category) => (
              <option key={category} value={category} />
            ))}
          </datalist>
        </label>
        <label>
          Tags (separadas por vírgula)
          <input type="text" name="tags" value={form.tags} onChange={handleChange} />
        </label>
      </div>
      {error && <p className="form-error">{error}</p>}
      <button type="submit" disabled={submitting}>
        {submitting ? 'Salvando...' : 'Adicionar gasto'}
      </button>
    </form>
  )
}
