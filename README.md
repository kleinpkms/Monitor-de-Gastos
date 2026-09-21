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
- editar tudo numa tabela, excluir lançamento linha a linha e exportar CSV;
- **entrar com a sua conta**: cada pessoa tem a própria base de lançamentos,
  categorias e limites, e não enxerga a das outras.

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
```

Antes do primeiro `streamlit run` é preciso configurar o login — é o passo da
próxima seção. Com o `.streamlit/secrets.toml` no lugar:

```bash
streamlit run app.py
```

O navegador abre em `http://localhost:8501` e mostra a tela de entrar. Na
primeira execução o banco é criado sozinho; a partir daí cada conta que entra
ganha as categorias padrão dela.

## Login: uma conta por pessoa

Quem cuida da identidade é o [Auth0](https://auth0.com) (gratuito até 25 mil
usuários por mês), pelo `st.login()` nativo do Streamlit. Na prática:

- o projeto **nunca vê nem guarda senha**. Quem faz senha, "esqueci minha
  senha", verificação de e-mail e "entrar com o Google" é o Auth0;
- o que fica na sua base é só o `sub` (o identificador da conta no token), o
  e-mail e o nome, na tabela `usuarios`;
- o `sub` — e não o e-mail — é o que liga a pessoa aos lançamentos dela, então
  trocar de e-mail no Auth0 não faz ninguém perder o histórico.

### 1. Criar a aplicação no Auth0

1. Crie uma conta em [auth0.com](https://auth0.com) e um tenant (ele vira um
   domínio do tipo `dev-ab12cd34.us.auth0.com`).
2. Em **Applications → Create Application**, escolha **Regular Web
   Application**. O tipo importa: é o único que recebe *client secret*, que o
   Streamlit precisa.
3. Na aba **Settings** da aplicação, anote **Domain**, **Client ID** e
   **Client Secret**.
4. Ainda em Settings, preencha (uma URL por linha):

   | Campo | Valor |
   | --- | --- |
   | Allowed Callback URLs | `http://localhost:8501/oauth2callback` |
   | Allowed Logout URLs | `http://localhost:8501` |
   | Allowed Web Origins | `http://localhost:8501` |

   Quando for para o Render, **acrescente** as mesmas três com a URL pública
   (`https://SEU-APP.onrender.com/oauth2callback` e assim por diante) — não
   troque, some, para continuar funcionando nos dois lugares. O
   `/oauth2callback` é fixo: é a rota que o Streamlit atende.
5. Se quiser o botão "Continuar com Google", ative em **Authentication →
   Social → Google**. Não é obrigatório: e-mail e senha já vêm ligados.

### 2. Configurar o projeto

```bash
cp secrets.toml.example .streamlit/secrets.toml
python -c "import secrets; print(secrets.token_hex(32))"   # cookie_secret
```

Abra `.streamlit/secrets.toml` e preencha os quatro valores: o `cookie_secret`
que acabou de gerar, o `client_id`, o `client_secret` e o
`server_metadata_url` (que é o seu domínio Auth0 com
`/.well-known/openid-configuration` no fim).

O arquivo tem segredo de verdade e **já está no `.gitignore`** — o que vai para
o repositório é só o `secrets.toml.example`.

### O que acontece com os lançamentos que já existem

Na primeira vez que o app sobe com esta versão, a base ganha a coluna
`usuario_id` e tudo que já estava gravado fica marcado como "sem dono" —
invisível na tela. **A primeira conta que fizer login herda esse acervo**, e as
contas seguintes começam vazias. Ou seja: entre você primeiro, antes de mandar
o link para alguém, e seu histórico continua onde estava.

A migração roda sozinha, nos dois bancos, e não precisa de comando. Vale o
backup de sempre antes: com SQLite é copiar o `financas.db`; no Neon, o painel
tem *branch/restore*.

### Restringindo quem entra (opcional)

Por padrão, qualquer pessoa que criar conta no seu tenant Auth0 ganha o próprio
dashboard, vazio. Se você quiser liberar só alguns e-mails, defina a variável
de ambiente `EMAILS_PERMITIDOS`:

```
EMAILS_PERMITIDOS=voce@exemplo.com,alguem@exemplo.com
```

Quem não estiver na lista entra no Auth0 mas para numa tela de "conta sem
acesso". Para fechar o cadastro de vez, o caminho é o próprio Auth0
(**Authentication → Database → Disable Sign Ups**).

Sem nenhum lançamento, a aba **Ajustes** tem um botão para gerar alguns meses
de dados fictícios, só para ver o dashboard cheio; depois é só apagar tudo.

## Banco de dados: SQLite ou Postgres

A escolha é automática, pela variável de ambiente `DATABASE_URL`:

| `DATABASE_URL` | O que acontece |
| --- | --- |
| não definida | usa o arquivo `financas.db` na pasta do projeto (SQLite) |
| definida | conecta no Postgres dessa URL |

O schema (tabelas `usuarios`, `lancamentos`, `categorias` e `orcamentos`) é
criado na primeira conexão nos dois casos. As três últimas têm uma coluna
`usuario_id`, e toda consulta do `database.py` filtra por ela.

Com mais de uma pessoa usando ao mesmo tempo, **prefira o Postgres**: o SQLite
serializa a escrita num arquivo só e, sob acesso simultâneo, começa a devolver
`database is locked`. Para uso individual ele continua perfeito.

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
| `auth.py` | o login pelo Auth0: tela de entrar, quem é o usuário da sessão e o botão de sair |
| `database.py` | acesso ao banco. Fala SQLite e Postgres pela mesma interface, cria o schema, migra a base antiga, e concentra inserir/atualizar/excluir, orçamentos e exportação — tudo já filtrado pelo usuário logado |
| `extrato.py` | leitura das faturas em PDF: extrai o texto, reconhece as transações, sugere categoria por palavra-chave e marca repetidos |
| `charts.py` | os gráficos Plotly, um por função |
| `config.py` | paleta, categorias padrão, palavras-chave da classificação automática e formatação de valores em real |
| `style.css` | o visual do dashboard (tema escuro minimalista) |
| `.streamlit/config.toml` | tema nativo do Streamlit, alinhado ao `style.css` |
| `secrets.toml.example` | modelo do `.streamlit/secrets.toml` com a configuração do Auth0 |
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
| `EMAILS_PERMITIDOS` | lista de e-mails liberados, separados por vírgula (opcional) |

O `DATABASE_URL` é o que importa de verdade: o disco do Render é efêmero, então
sem um banco externo o `financas.db` é apagado a cada deploy ou reinício e você
perde os lançamentos. Com o Neon configurado, os dados sobrevivem a qualquer
redeploy. Com login, ele deixa de ser só conveniência: em SQLite efêmero cada
reinício apagaria também a tabela `usuarios`.

### O login em produção

O `secrets.toml` não vai no repositório, então ele entra no Render como
**Secret File** (aba *Environment* → *Secret Files*):

- **Filename:** `.streamlit/secrets.toml`
- **Contents:** o mesmo conteúdo do seu arquivo local, com **uma** diferença —
  o `redirect_uri` apontando para a URL pública:

```toml
redirect_uri = "https://SEU-APP.onrender.com/oauth2callback"
```

E no Auth0, em **Applications → sua aplicação → Settings**, acrescente às três
listas a URL do Render (`https://SEU-APP.onrender.com/oauth2callback` nas
callbacks, `https://SEU-APP.onrender.com` nas outras duas), mantendo as de
`localhost` se quiser continuar rodando na sua máquina.

Se o login voltar com `Callback URL mismatch`, é quase sempre isto: o
`redirect_uri` do `secrets.toml` e a *Allowed Callback URL* do Auth0 têm de ser
idênticos, caractere por caractere — `http` × `https`, barra no fim, tudo conta.

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
