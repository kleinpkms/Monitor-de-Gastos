export const COLORS = {
  surface: '#1a1a19',
  grid: '#2c2c2a',
  border: 'rgba(255, 255, 255, 0.1)',
  textPrimary: '#ffffff',
  textSecondary: '#c3c2b7',
  muted: '#898781',
  accent: '#3987e5',
  danger: '#e66767',
}

export const currencyFormatter = new Intl.NumberFormat('pt-BR', {
  style: 'currency',
  currency: 'BRL',
})

export const compactCurrencyFormatter = new Intl.NumberFormat('pt-BR', {
  style: 'currency',
  currency: 'BRL',
  notation: 'compact',
})
