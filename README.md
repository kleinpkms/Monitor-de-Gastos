# Dashboard financeiro

Controle de gastos pessoais em [Streamlit](https://streamlit.io): você lança
receitas e despesas, define limites por categoria e acompanha para onde o
dinheiro foi — com importação das faturas de cartão em PDF, para não precisar
digitar compra por compra.

O que dá para fazer:

- lançar receitas e despesas com categoria, forma de pagamento e marcação de
  "repete todo mês" (que pode ser copiada para o mês seguinte com um clique);
- ver o mês em gráficos: rosca por categoria, entradas × saídas × saldo dos
  últimos meses, ritmo de gasto acumulado e maiores gastos;
- definir um limite mensal por categoria e acompanhar quanto já foi usado;
- **importar faturas de cartão em PDF**, inclusive várias de uma vez e de meses
  diferentes, com as categorias já sugeridas por palavra-chave;
- editar tudo numa tabela, excluir lançamento linha a linha e exportar CSV.

Os dados ficam num SQLite local por padrão, ou num Postgres quando existe a
variável `DATABASE_URL` — é a mesma aplicação nos dois casos.

## Rodando local, do zero

Precisa de Python 3.10 ou mais novo.

```bash
git clone https://github.com/kleinpkms/Monitor-de-Gastos.git
cd Monitor-de-Gastos

python -m venv .venv
# Windows (PowerShell):
.venv\Scripts\Activate.ps1
# Linux / macOS:
source .venv/bin/activate

pip install -r requirements.txt
streamlit run app.py
```

O navegador abre em `http://localhost:8501`. Na primeira execução o banco é
criado sozinho, com as categorias padrão — não há passo de migração.

Sem nenhum lançamento, a aba **Ajustes** tem um botão para gerar alguns meses
de dados fictícios, só para ver o dashboard cheio; depois é só apagar tudo.

## Banco de dados: SQLite ou Postgres

A escolha é automática, pela variável de ambiente `DATABASE_URL`:

| `DATABASE_URL` | O que acontece |
| --- | --- |
| não definida | usa o arquivo `financas.db` na pasta do projeto (SQLite) |
| definida | conecta no Postgres dessa URL |

O schema (tabelas `lancamentos`, `categorias` e `orcamentos`) é criado na
primeira conexão nos dois casos.

Para usar um Postgres gratuito do [Neon](https://neon.tech) também na sua
máquina, copie a *connection string* do painel deles e escolha um dos dois
caminhos:

**Arquivo `.env`** (mais prático — já está no `.gitignore`), na raiz do projeto:

```
DATABASE_URL=postgresql://usuario:senha@ep-algo-123456.sa-east-1.aws.neon.tech/neondb?sslmode=require
```

**Ou variável manual**, a cada sessão do terminal:

```bash
# Linux / macOS
export DATABASE_URL="postgresql://usuario:senha@ep-algo.neon.tech/neondb?sslmode=require"

# Windows (PowerShell)
$env:DATABASE_URL = "postgresql://usuario:senha@ep-algo.neon.tech/neondb?sslmode=require"
```

Se a URL não trouxer `sslmode`, o projeto acrescenta `sslmode=require` sozinho,
que é o que o Neon exige. O cabeçalho do dashboard mostra onde está gravando,
então dá para conferir de olho se pegou o Postgres ou o SQLite.

Para voltar ao SQLite, basta remover a variável (ou apagar a linha do `.env`).

## Arquivos do projeto

| Arquivo | Para que serve |
| --- | --- |
| `app.py` | a tela inteira: barra lateral, cartões do topo e as cinco abas (Visão geral, Lançamentos, Importar extrato, Orçamento, Ajustes) |
| `database.py` | acesso ao banco. Fala SQLite e Postgres pela mesma interface, cria o schema, e concentra inserir/atualizar/excluir, orçamentos e exportação |
| `extrato.py` | leitura das faturas em PDF: extrai o texto, reconhece as transações, sugere categoria por palavra-chave e marca repetidos |
| `charts.py` | os gráficos Plotly, um por função |
| `config.py` | paleta, categorias padrão, palavras-chave da classificação automática e formatação de valores em real |
| `style.css` | o visual do dashboard (tema escuro minimalista) |
| `.streamlit/config.toml` | tema nativo do Streamlit, alinhado ao `style.css` |
| `requirements.txt` | dependências |

O arquivo `financas.db` **não vai para o repositório** — ele tem seus dados
reais e já está no `.gitignore`, junto com `.env` e
`.streamlit/secrets.toml`. Se um dia ele aparecer no `git status`, não comite:
confira se a linha `financas.db` continua no `.gitignore`.

## Deploy no Render

Crie um *Web Service* apontando para este repositório e preencha:

- **Build Command:** `pip install -r requirements.txt`
- **Start Command:** `streamlit run app.py --server.port $PORT --server.address 0.0.0.0`

A flag `--server.port $PORT` é obrigatória: o Render injeta a porta e faz a
verificação nela.

Em **Environment**, adicione:

| Variável | Valor |
| --- | --- |
| `DATABASE_URL` | a connection string do Neon |
| `SENHA_EXTRATO` | a senha das suas faturas em PDF (opcional) |

O `DATABASE_URL` é o que importa de verdade: o disco do Render é efêmero, então
sem um banco externo o `financas.db` é apagado a cada deploy ou reinício e você
perde os lançamentos. Com o Neon configurado, os dados sobrevivem a qualquer
redeploy.

## Importando a fatura do cartão

Na aba **Importar extrato**:

1. **Envie os PDFs.** Pode arrastar vários de uma vez, de meses diferentes —
   cada arquivo é lido separadamente.
2. **Preencha a senha**, se a fatura vier protegida (o banco costuma mandar
   assim). A mesma senha vale para todos os arquivos do envio. Ela também pode
   ficar guardada em `SENHA_EXTRATO` ou em `.streamlit/secrets.toml`.
3. Clique em **Ler fatura(s)**. Aparece um resumo por arquivo com a quantidade
   de transações e o período que cada um cobre.
4. **Revise a tabela consolidada.** Dá para corrigir descrição, categoria, tipo
   e valor de cada linha, e desmarcar o que não quiser importar. A coluna
   *Situação* avisa o que já existe na base ou veio repetido no próprio envio.
5. Clique em **Confirmar importação**. Cada lançamento entra no mês da data da
   própria transação, então uma fatura antiga vai para o mês dela — troque o
   *Mês de referência* na barra lateral para ver o resultado.

Detalhes que costumam gerar dúvida:

- o **mês vem sempre da data da linha**; o campo "Ano de reserva" só é usado se
  alguma linha vier sem o ano, o que é raro;
- linhas de **pagamento da fatura e estorno** (valor com `+` na fatura do Inter)
  são puladas de propósito — elas abatem a fatura, não são despesa;
- a seção **"Próxima fatura"** (compras futuras e parcelas a vencer) é
  descartada; essas compras entram quando a fatura delas chegar;
- **repetidos** são detectados por data + descrição + valor em toda a base, em
  qualquer mês, então reimportar a mesma fatura não duplica nada;
- sem palavra-chave correspondente, a transação entra como **"Não atribuído"**
  em vez de sumir. As regras de classificação ficam em
  `PALAVRAS_CHAVE_CATEGORIA`, no `config.py`, e são suas para editar;
- se nada for reconhecido, abra **"Texto extraído dos PDFs"**: além do texto de
  cada página, ele mostra o `repr()` das linhas que pareciam lançamento, o que
  revela caractere invisível quebrando o padrão. Fatura digitalizada (imagem)
  não tem texto para extrair e precisaria de OCR.
