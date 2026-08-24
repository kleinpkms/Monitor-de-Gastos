import { useState } from 'react'
import { bulkCreateExpenses, parseInvoice } from '../services/api.js'

const MONTH_LABELS = [
  'Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
  'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro',
]

const today = new Date()

export default function ImportInvoice({ categories, onImported }) {
  const [expanded, setExpanded] = useState(false)
  const [file, setFile] = useState(null)
  const [password, setPassword] = useState('')
  const [referenceMonth, setReferenceMonth] = useState(today.getMonth() + 1)
  const [referenceYear, setReferenceYear] = useState(today.getFullYear())
  const [rows, setRows] = useState([])
  const [parsing, setParsing] = useState(false)
  const [parseError, setParseError] = useState(null)
  const [confirming, setConfirming] = useState(false)
  const [confirmError, setConfirmError] = useState(null)
  const [successMessage, setSuccessMessage] = useState(null)

  async function handleParse(event) {
    event.preventDefault()
    if (!file) return
    setParsing(true)
    setParseError(null)
    setSuccessMessage(null)
    try {
      const transactions = await parseInvoice(file, referenceMonth, referenceYear, password)
      setRows(transactions)
    } catch (err) {
      setParseError(err?.response?.data?.detail ?? 'Não foi possível processar o PDF.')
      setRows([])
    } finally {
      setParsing(false)
    }
  }

  function updateRow(index, field, value) {
    setRows((prev) => prev.map((row, i) => (i === index ? { ...row, [field]: value } : row)))
  }

  const selectedRows = rows.filter((row) => row.include)
  const missingCategory = selectedRows.some((row) => !row.category.trim())

  async function handleConfirm() {
    setConfirming(true)
    setConfirmError(null)
    try {
      const items = selectedRows.map((row) => ({
        amount: Number(row.amount),
        description: row.description.trim(),
        date: row.date,
        category: row.category.trim(),
        tags: [],
      }))
      const result = await bulkCreateExpenses(items)
      setSuccessMessage(`${result.created} lançamento(s) importado(s) com sucesso.`)
      setRows([])
      setFile(null)
      await onImported()
    } catch (err) {
      setConfirmError(err?.response?.data?.detail ?? 'Não foi possível importar os lançamentos.')
    } finally {
      setConfirming(false)
    }
  }

  return (
    <div className="card import-card">
      <div className="import-header">
        <h2>Importar fatura (PDF)</h2>
        <button type="button" className="ghost" onClick={() => setExpanded((value) => !value)}>
          {expanded ? 'Fechar' : 'Importar'}
        </button>
      </div>

      {expanded && (
        <>
          <form className="import-form" onSubmit={handleParse}>
            <label>
              Arquivo PDF
              <input
                type="file"
                accept="application/pdf"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                required
              />
            </label>
            <label>
              Senha do PDF (se houver)
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="opcional"
                autoComplete="off"
              />
            </label>
            <label>
              Mês de referência
              <select value={referenceMonth} onChange={(e) => setReferenceMonth(Number(e.target.value))}>
                {MONTH_LABELS.map((monthLabel, index) => (
                  <option key={monthLabel} value={index + 1}>
                    {monthLabel}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Ano de referência
              <input
                type="number"
                value={referenceYear}
                onChange={(e) => setReferenceYear(Number(e.target.value))}
              />
            </label>
            <button type="submit" disabled={!file || parsing}>
              {parsing ? 'Analisando...' : 'Analisar PDF'}
            </button>
          </form>

          {parseError && <p className="form-error">{parseError}</p>}
          {successMessage && <p className="import-success">{successMessage}</p>}

          {rows.length > 0 && (
            <>
              <p className="muted import-hint">
                Confira os lançamentos reconhecidos, ajuste o que for preciso e desmarque o que não deve ser
                importado (ex.: pagamentos da própria fatura).
              </p>
              <div className="table-wrapper">
                <table>
                  <thead>
                    <tr>
                      <th />
                      <th>Data</th>
                      <th>Descrição</th>
                      <th>Categoria</th>
                      <th className="align-right">Valor</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((row, index) => (
                      <tr key={index} className={row.include ? '' : 'row-excluded'}>
                        <td>
                          <input
                            type="checkbox"
                            checked={row.include}
                            onChange={(e) => updateRow(index, 'include', e.target.checked)}
                          />
                        </td>
                        <td>
                          <input
                            type="date"
                            value={row.date}
                            onChange={(e) => updateRow(index, 'date', e.target.value)}
                          />
                        </td>
                        <td>
                          <input
                            type="text"
                            value={row.description}
                            onChange={(e) => updateRow(index, 'description', e.target.value)}
                          />
                        </td>
                        <td>
                          <input
                            type="text"
                            list="category-options-import"
                            value={row.category}
                            onChange={(e) => updateRow(index, 'category', e.target.value)}
                            placeholder="Categoria"
                          />
                        </td>
                        <td className="align-right">
                          <input
                            type="number"
                            step="0.01"
                            min="0.01"
                            value={row.amount}
                            onChange={(e) => updateRow(index, 'amount', e.target.value)}
                          />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <datalist id="category-options-import">
                  {categories.map((category) => (
                    <option key={category} value={category} />
                  ))}
                </datalist>
              </div>

              {missingCategory && (
                <p className="form-error">Preencha a categoria de todos os lançamentos selecionados.</p>
              )}
              {confirmError && <p className="form-error">{confirmError}</p>}

              <button
                type="button"
                onClick={handleConfirm}
                disabled={selectedRows.length === 0 || missingCategory || confirming}
              >
                {confirming ? 'Importando...' : `Confirmar importação (${selectedRows.length})`}
              </button>
            </>
          )}
        </>
      )}
    </div>
  )
}
