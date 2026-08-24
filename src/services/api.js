import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
})

export async function listExpenses(params = {}) {
  const { data } = await api.get('/expenses', { params })
  return data
}

export async function createExpense(payload) {
  const { data } = await api.post('/expenses', payload)
  return data
}

export async function updateExpense(id, payload) {
  const { data } = await api.put(`/expenses/${id}`, payload)
  return data
}

export async function deleteExpense(id) {
  await api.delete(`/expenses/${id}`)
}

export async function getSummary(params = {}) {
  const { data } = await api.get('/expenses/summary', { params })
  return data
}

export async function listCategories() {
  const { data } = await api.get('/categories')
  return data
}

export async function bulkCreateExpenses(items) {
  const { data } = await api.post('/expenses/bulk', { items })
  return data
}

export async function parseInvoice(file, referenceMonth, referenceYear) {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('reference_month', referenceMonth)
  formData.append('reference_year', referenceYear)
  const { data } = await api.post('/imports/parse', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

export default api
