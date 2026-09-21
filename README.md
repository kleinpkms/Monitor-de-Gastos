# Dashboard financeiro

Controle de gastos mensais em Python — roda na sua máquina, guarda tudo em um
único arquivo SQLite e não manda nada para lugar nenhum.

## Rodando

```bash
cd dashboard-financeiro
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

Abre em `http://localhost:8501`. Na primeira vez a base vem vazia — em
**Ajustes → Gerar dados de exemplo** você cria seis meses fictícios para ver o
dashboard cheio, e depois apaga tudo com um clique.

## O que tem em cada aba

| Aba | Serve para |
|---|---|
| Visão geral | Saldo do mês, divisão por categoria, evolução dos últimos meses, ritmo de gasto acumulado, maiores despesas e formas de pagamento |
| Lançamentos | Planilha editável: altere qualquer célula, adicione pela linha vazia do fim, apague pela lixeira e clique em *Salvar alterações* |
| Orçamento | Limite mensal por categoria com barra de progresso. A marca vertical mostra onde você deveria estar considerando o dia de hoje |
| Ajustes | Criar/remover categorias, importar e exportar CSV, gerar exemplos, zerar a base |

Lançamentos marcados como **fixo** (aluguel, assinaturas, mensalidade) podem ser
copiados para o mês seguinte com o botão da barra lateral — sem redigitar nada.

## Arquivos

```
app.py         interface e regras de tela
database.py    SQLite: schema, CRUD, importação/exportação
charts.py      gráficos Plotly
config.py      paleta, categorias padrão, formatação de moeda
style.css      tipografia e componentes visuais
financas.db    criado no primeiro uso (é o seu backup: basta copiar)
```

## Importando um CSV do banco

Colunas obrigatórias: `data`, `descricao`, `categoria`, `tipo`, `valor`.
Opcionais: `metodo`, `fixo`, `obs`. Datas aceitas em `2026-03-08` ou `08/03/2026`;
valores com vírgula ou ponto. Categoria que não existir é criada automaticamente.

## Ajustes rápidos

- **Cores e categorias**: `config.py`, lista `CATEGORIAS_PADRAO`.
- **Tema**: variáveis no topo de `style.css` e `TEMA` em `config.py`.
- **Novo gráfico**: escreva a função em `charts.py` devolvendo uma figura Plotly
  e chame com `st.plotly_chart(...)` na aba desejada.
- **Trocar a porta**: `.streamlit/config.toml`.

## Quando quiser colocar no ar

O jeito mais curto é Streamlit Community Cloud (grátis, conecta no repositório do
GitHub). Um ponto de atenção: o disco lá é efêmero, então o `financas.db` some a
cada reinício. Para uso online vale trocar o SQLite por Postgres — como todo o
acesso a dados está isolado em `database.py`, é só reescrever as funções desse
arquivo. E antes de expor na internet, coloque uma senha na frente.
