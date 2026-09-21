"""
Camada de dados do dashboard, que fala dois bancos:

* sem `DATABASE_URL` no ambiente, grava num arquivo SQLite (`financas.db`)
  ao lado do projeto — é só copiar esse arquivo para levar seus dados;
* com `DATABASE_URL` (ex.: a connection string do Neon), usa Postgres.

O resto do app não sabe a diferença: `conectar()` devolve sempre o mesmo
objeto, que traduz os `?` para `%s` e cuida do dialeto quando é Postgres.
O schema é criado sozinho na primeira conexão, nos dois casos.

Cada linha pertence a um usuário
--------------------------------
`lancamentos`, `categorias` e `orcamentos` têm uma coluna `usuario_id`, e
toda consulta daqui filtra por ela. Quem é o dono não viaja em parâmetro
função por função: o `auth.py` chama `definir_usuario()` uma vez no começo
do rerun e as funções leem daí. O valor fica num `threading.local`, porque
cada sessão do Streamlit roda o script na sua própria thread — assim duas
pessoas logadas ao mesmo tempo não enxergam uma a base da outra.

Se ninguém chamou `definir_usuario()`, as funções levantam `PermissionError`
em vez de responder a base inteira. É de propósito: um esquecimento vira
erro na tela, não vazamento de dados de outra pessoa.
"""

from __future__ import annotations

import os
import random
import sqlite3
import threading
from datetime import date, datetime, timedelta, timezone

import pandas as pd

from config import (CATEGORIA_NAO_ATRIBUIDA, CATEGORIAS_PADRAO,
                    CORES_ANTIGAS_PADRAO)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _carregar_dotenv() -> None:
    """Lê um .env ao lado do projeto, se o python-dotenv estiver instalado."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(os.path.join(BASE_DIR, ".env"))


_carregar_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
USANDO_POSTGRES = bool(DATABASE_URL)
DB_PATH = os.environ.get("FINANCAS_DB", os.path.join(BASE_DIR, "financas.db"))

# Teto de conexões simultâneas no Postgres. Uma por sessão ativa é o pior
# caso; o Neon no plano gratuito aguenta bem mais que isso.
PG_MAX_CONEXOES = int(os.environ.get("PG_MAX_CONEXOES", "8"))

# Dono de fachada das linhas que existiam antes do login. Nenhum usuário
# de verdade tem id 0 (tanto o AUTOINCREMENT quanto o SERIAL começam em 1),
# então essas linhas ficam invisíveis para todo mundo até que o primeiro
# usuário a entrar as adote — ver `_adotar_orfaos`.
USUARIO_ORFAO = 0

_pg_pool = None
_pg_trava = threading.Lock()
_schema_pronto = False

# Quem está logado nesta thread/sessão.
_sessao = threading.local()


def onde_estou_gravando() -> str:
    """Frase curta para a tela dizer onde os dados estão."""
    if not USANDO_POSTGRES:
        return f"SQLite em {os.path.basename(DB_PATH)}"
    depois_do_arroba = DATABASE_URL.rsplit("@", 1)[-1]
    return f"Postgres em {depois_do_arroba.split('/')[0]}"


# --------------------------------------------------- usuário da sessão

def definir_usuario(usuario_id: int | None) -> None:
    """Marca de quem são as linhas desta sessão. Chamado a cada rerun."""
    _sessao.usuario_id = int(usuario_id) if usuario_id is not None else None


def usuario_atual() -> int | None:
    return getattr(_sessao, "usuario_id", None)


def _uid() -> int:
    """Id do dono, ou estoura. Nunca devolve None para virar filtro vazio."""
    usuario_id = usuario_atual()
    if usuario_id is None:
        raise PermissionError(
            "Nenhum usuário ativo nesta sessão — faça login antes de ler ou "
            "gravar. (database.definir_usuario não foi chamado neste rerun.)"
        )
    return usuario_id


# --------------------------------------------------------- conexão

def _url_com_ssl() -> str:
    url = DATABASE_URL
    if "sslmode=" not in url:  # Neon (e o Render) exigem TLS
        url += ("&" if "?" in url else "?") + "sslmode=require"
    return url


def _pool():
    """Pool preguiçoso, criado na primeira consulta.

    Antes daqui existia uma conexão só, compartilhada por todo o processo.
    Isso servia enquanto o dashboard era de uma pessoa, mas com várias
    sessões ao mesmo tempo o `commit()` de uma confirmaria a transação
    ainda aberta da outra — e o `rollback()` jogaria fora o que a outra
    acabou de gravar. Cada `Conexao` agora pega uma conexão só para ela e
    devolve no fim, então as transações não se cruzam. O pool continua
    poupando o custo de reconectar a cada rerun, que era a razão de ser da
    conexão única.
    """
    global _pg_pool
    with _pg_trava:
        if _pg_pool is None:
            from psycopg2.pool import ThreadedConnectionPool

            _pg_pool = ThreadedConnectionPool(1, PG_MAX_CONEXOES, _url_com_ssl())
        return _pg_pool


def _pegar_postgres():
    """Tira uma conexão do pool, conferindo se ela sobreviveu.

    O Neon dorme e derruba conexão parada, então a que estava guardada
    pode voltar morta: o `SELECT 1` detecta, ela é descartada de vez
    (`close=True`) e o pool abre outra.
    """
    import psycopg2

    pool = _pool()
    for _ in range(3):
        con = pool.getconn()
        try:
            con.autocommit = False
            with con.cursor() as teste:
                teste.execute("SELECT 1")
            con.rollback()
            return con
        except psycopg2.Error:
            pool.putconn(con, close=True)
    raise RuntimeError("Não consegui uma conexão viva com o Postgres.")


def _devolver_postgres(con, quebrou: bool) -> None:
    try:
        _pool().putconn(con, close=quebrou)
    except Exception:  # pool já fechado (shutdown) — nada a fazer
        pass


class Conexao:
    """Fachada fina sobre sqlite3/psycopg2 com a mesma cara para o app.

    Aceita sempre `?` como placeholder e devolve linhas acessíveis por
    nome de coluna, como o `sqlite3.Row` já fazia.
    """

    def __init__(self) -> None:
        self.postgres = USANDO_POSTGRES
        if self.postgres:
            self.bruta = _pegar_postgres()
        else:
            self.bruta = sqlite3.connect(DB_PATH, check_same_thread=False)
            self.bruta.row_factory = sqlite3.Row
            self.bruta.execute("PRAGMA foreign_keys = ON")

    # -- tradução de dialeto ------------------------------------------
    def traduzir(self, sql: str) -> str:
        return sql.replace("?", "%s") if self.postgres else sql

    def execute(self, sql: str, params=()):
        if not self.postgres:
            return self.bruta.execute(sql, params)
        from psycopg2.extras import RealDictCursor

        cur = self.bruta.cursor(cursor_factory=RealDictCursor)
        cur.execute(self.traduzir(sql), params)
        return cur

    def executemany(self, sql: str, sequencia) -> None:
        if not self.postgres:
            self.bruta.executemany(sql, sequencia)
            return
        with self.bruta.cursor() as cur:
            cur.executemany(self.traduzir(sql), list(sequencia))

    def executescript(self, script: str) -> None:
        if not self.postgres:
            self.bruta.executescript(script)
            return
        with self.bruta.cursor() as cur:
            for comando in script.split(";"):
                if comando.strip():
                    cur.execute(comando)

    def ler_df(self, sql: str, params=()) -> pd.DataFrame:
        return pd.read_sql_query(self.traduzir(sql), self.bruta, params=list(params))

    # -- contexto ------------------------------------------------------
    def __enter__(self) -> "Conexao":
        return self

    def __exit__(self, tipo, valor, tb) -> None:
        if not self.postgres:
            if tipo is None:
                self.bruta.commit()
            else:
                self.bruta.rollback()
            self.bruta.close()
            return

        quebrou = False
        try:
            if tipo is None:
                self.bruta.commit()
            else:
                self.bruta.rollback()
        except Exception:
            quebrou = True  # conexão morreu no meio: não volta para o pool
            raise
        finally:
            _devolver_postgres(self.bruta, quebrou)


def conectar() -> Conexao:
    return Conexao()


# ------------------------------------------------------------ schema

# As duas tabelas que a migração precisa refazer no SQLite ficam em
# constantes próprias, para o rebuild recriar exatamente a mesma coisa que
# a base nova recebe — e não uma cópia que sai do lugar com o tempo.
_TABELA_CATEGORIAS_SQLITE = """
    CREATE TABLE IF NOT EXISTS categorias (
        usuario_id INTEGER NOT NULL,
        nome  TEXT NOT NULL,
        tipo  TEXT NOT NULL CHECK (tipo IN ('despesa','receita')),
        cor   TEXT NOT NULL DEFAULT '#8A9AAB',
        icone TEXT NOT NULL DEFAULT '📦',
        PRIMARY KEY (usuario_id, nome)
    )
"""

_TABELA_ORCAMENTOS_SQLITE = """
    CREATE TABLE IF NOT EXISTS orcamentos (
        usuario_id INTEGER NOT NULL,
        categoria TEXT NOT NULL,
        limite    REAL NOT NULL,
        PRIMARY KEY (usuario_id, categoria)
    )
"""

_SCHEMA_SQLITE = f"""
    CREATE TABLE IF NOT EXISTS usuarios (
        id        INTEGER PRIMARY KEY AUTOINCREMENT,
        sub       TEXT NOT NULL UNIQUE,
        email     TEXT NOT NULL DEFAULT '',
        nome      TEXT NOT NULL DEFAULT '',
        criado_em TEXT NOT NULL
    );

    {_TABELA_CATEGORIAS_SQLITE};

    CREATE TABLE IF NOT EXISTS lancamentos (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        usuario_id INTEGER NOT NULL,
        data      TEXT NOT NULL,
        descricao TEXT NOT NULL,
        categoria TEXT NOT NULL,
        tipo      TEXT NOT NULL CHECK (tipo IN ('despesa','receita')),
        valor     REAL NOT NULL,
        metodo    TEXT DEFAULT 'Pix',
        fixo      INTEGER NOT NULL DEFAULT 0,
        obs       TEXT DEFAULT ''
    );

    {_TABELA_ORCAMENTOS_SQLITE};

    CREATE TABLE IF NOT EXISTS compartilhamentos (
        dono_id   INTEGER NOT NULL,
        email     TEXT NOT NULL,
        criado_em TEXT NOT NULL,
        PRIMARY KEY (dono_id, email)
    );
"""

# Mesmas tabelas em Postgres: SERIAL no lugar do AUTOINCREMENT e
# DOUBLE PRECISION no lugar do REAL (o REAL do Postgres é de 4 bytes e
# perderia centavos). A coluna `data` segue TEXT nos dois, para o
# substr(data,1,7) das competências continuar idêntico.
_SCHEMA_POSTGRES = """
    CREATE TABLE IF NOT EXISTS usuarios (
        id        SERIAL PRIMARY KEY,
        sub       TEXT NOT NULL UNIQUE,
        email     TEXT NOT NULL DEFAULT '',
        nome      TEXT NOT NULL DEFAULT '',
        criado_em TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS categorias (
        usuario_id INTEGER NOT NULL,
        nome  TEXT NOT NULL,
        tipo  TEXT NOT NULL CHECK (tipo IN ('despesa','receita')),
        cor   TEXT NOT NULL DEFAULT '#8A9AAB',
        icone TEXT NOT NULL DEFAULT '📦',
        PRIMARY KEY (usuario_id, nome)
    );

    CREATE TABLE IF NOT EXISTS lancamentos (
        id         SERIAL PRIMARY KEY,
        usuario_id INTEGER NOT NULL,
        data      TEXT NOT NULL,
        descricao TEXT NOT NULL,
        categoria TEXT NOT NULL,
        tipo      TEXT NOT NULL CHECK (tipo IN ('despesa','receita')),
        valor     DOUBLE PRECISION NOT NULL,
        metodo    TEXT DEFAULT 'Pix',
        fixo      INTEGER NOT NULL DEFAULT 0,
        obs       TEXT DEFAULT ''
    );

    CREATE TABLE IF NOT EXISTS orcamentos (
        usuario_id INTEGER NOT NULL,
        categoria TEXT NOT NULL,
        limite    DOUBLE PRECISION NOT NULL,
        PRIMARY KEY (usuario_id, categoria)
    );

    CREATE TABLE IF NOT EXISTS compartilhamentos (
        dono_id   INTEGER NOT NULL,
        email     TEXT NOT NULL,
        criado_em TEXT NOT NULL,
        PRIMARY KEY (dono_id, email)
    );
"""


def criar_schema(forcar: bool = False) -> None:
    """Cria as tabelas e migra a base antiga. Roda sozinho na primeira conexão.

    As categorias padrão não entram mais aqui: agora são por usuário, e
    nascem em `garantir_usuario`. O app chama isso a cada rerun; a trava
    `_schema_pronto` evita repetir o DDL inteiro (que no Postgres custaria
    uma ida à rede por rerun).
    """
    global _schema_pronto
    if _schema_pronto and not forcar:
        return

    with conectar() as con:
        con.executescript(_SCHEMA_POSTGRES if con.postgres else _SCHEMA_SQLITE)
        _migrar(con)
        # Só depois da migração: numa base antiga a coluna `usuario_id` ainda
        # não existia quando o CREATE TABLE acima passou batido, e o índice
        # sobre ela falharia.
        con.execute("CREATE INDEX IF NOT EXISTS idx_lanc_usuario_data "
                    "ON lancamentos(usuario_id, data)")
        con.execute("DROP INDEX IF EXISTS idx_lanc_data")  # superado pelo acima

    _schema_pronto = True


# ----------------------------------------------------------- migração

def _colunas(con: Conexao, tabela: str) -> set[str]:
    if con.postgres:
        linhas = con.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = current_schema() AND table_name = ?",
            (tabela,),
        ).fetchall()
        return {l["column_name"] for l in linhas}
    return {l["name"] for l in con.execute(f"PRAGMA table_info({tabela})").fetchall()}


def _migrar(con: Conexao) -> None:
    """Leva uma base de dono único para o formato com `usuario_id`.

    Em base nova não faz nada: o `CREATE TABLE` acima já saiu com a coluna.
    Em base antiga as tabelas existem no formato velho e o `IF NOT EXISTS`
    passou batido, então é aqui que elas mudam. Tudo que já estava gravado
    recebe `usuario_id = 0` e some da tela até o primeiro login adotar.
    """
    # DDL não aceita parâmetro ligado (nem no SQLite nem no Postgres), então
    # o valor entra interpolado — é uma constante inteira nossa, não entrada
    # de usuário.
    if "usuario_id" not in _colunas(con, "lancamentos"):
        con.execute(
            f"ALTER TABLE lancamentos ADD COLUMN usuario_id INTEGER NOT NULL "
            f"DEFAULT {USUARIO_ORFAO}"
        )

    # `categorias` e `orcamentos` tinham o nome como chave primária, o que
    # impediria duas pessoas de terem uma categoria "Mercado". A chave passa
    # a ser (usuario_id, nome) — e trocar chave primária dá mais trabalho no
    # SQLite, que não sabe alterá-la e exige refazer a tabela.
    if "usuario_id" not in _colunas(con, "categorias"):
        _trocar_chave(
            con, "categorias",
            colunas="nome, tipo, cor, icone",
            chave="nome",
            ddl_sqlite=_TABELA_CATEGORIAS_SQLITE,
        )
    if "usuario_id" not in _colunas(con, "orcamentos"):
        _trocar_chave(
            con, "orcamentos",
            colunas="categoria, limite",
            chave="categoria",
            ddl_sqlite=_TABELA_ORCAMENTOS_SQLITE,
        )


def _nome_da_pk(con: Conexao, tabela: str) -> str | None:
    """Nome real da chave primária no catálogo do Postgres.

    Dá para adivinhar `<tabela>_pkey`, que é como o Postgres batiza quando
    ninguém nomeia — mas se o nome for outro o DROP não acha nada, o ADD
    seguinte esbarra em "multiple primary keys" e a migração morre no meio.
    Perguntar custa uma consulta e tira a suposição do caminho.
    """
    linha = con.execute(
        "SELECT conname FROM pg_constraint "
        "WHERE conrelid = ?::regclass AND contype = 'p'",
        (tabela,),
    ).fetchone()
    return linha["conname"] if linha else None


def _trocar_chave(con: Conexao, tabela: str, colunas: str, chave: str,
                  ddl_sqlite: str) -> None:
    if con.postgres:
        con.execute(
            f"ALTER TABLE {tabela} ADD COLUMN usuario_id INTEGER NOT NULL "
            f"DEFAULT {USUARIO_ORFAO}"
        )
        pk = _nome_da_pk(con, tabela)
        if pk:
            con.execute(f'ALTER TABLE {tabela} DROP CONSTRAINT "{pk}"')
        con.execute(f"ALTER TABLE {tabela} ADD PRIMARY KEY (usuario_id, {chave})")
        return

    # SQLite não sabe alterar chave primária: renomeia a antiga, recria no
    # formato novo e copia as linhas.
    antiga = f"{tabela}_antes_do_login"
    con.execute(f"DROP TABLE IF EXISTS {antiga}")  # sobra de migração interrompida
    con.execute(f"ALTER TABLE {tabela} RENAME TO {antiga}")
    con.execute(ddl_sqlite)
    con.execute(
        f"INSERT INTO {tabela} (usuario_id, {colunas}) "
        f"SELECT {USUARIO_ORFAO}, {colunas} FROM {antiga}"
    )
    con.execute(f"DROP TABLE {antiga}")


# ---------------------------------------------------------- usuários

def garantir_usuario(sub: str, email: str = "", nome: str = "") -> int:
    """Acha (ou cria) o usuário dono do `sub` vindo do login. Devolve o id.

    O `sub` é o identificador do token do Auth0 — não o e-mail, que a pessoa
    pode trocar. Usuário novo ganha as categorias padrão; o primeiro de
    todos também herda o que já estava na base antes de existir login.
    """
    criar_schema()
    with conectar() as con:
        linha = con.execute("SELECT id FROM usuarios WHERE sub = ?", (sub,)).fetchone()
        if linha:
            usuario_id = int(linha["id"])
            con.execute(
                "UPDATE usuarios SET email = ?, nome = ? WHERE id = ?",
                (email or "", nome or "", usuario_id),
            )
            # Também para quem já existe: é assim que uma categoria padrão
            # criada depois (Carro, Não atribuído…) chega a quem entrou antes
            # dela. Roda uma vez por sessão, não por rerun.
            _semear_categorias(con, usuario_id)
            return usuario_id

        primeiro = con.execute("SELECT COUNT(*) AS n FROM usuarios").fetchone()["n"] == 0
        sql = "INSERT INTO usuarios (sub, email, nome, criado_em) VALUES (?,?,?,?)"
        if con.postgres:
            sql += " RETURNING id"
        cur = con.execute(
            sql,
            (sub, email or "", nome or "", datetime.now(timezone.utc).isoformat(timespec="seconds")),
        )
        usuario_id = int(cur.fetchone()["id"]) if con.postgres else int(cur.lastrowid)

        if primeiro:
            _adotar_orfaos(con, usuario_id)
        _semear_categorias(con, usuario_id)
        return usuario_id


# ----------------------------------------------------- compartilhamento
# O dono convida por e-mail; quem foi convidado passa a poder escolher a
# base dele no seletor da barra lateral e mexe nela como se fosse sua —
# é assim que um casal usa uma conta em conjunto sem perder a própria.
# O convite é gravado pelo e-mail, e não pelo id, porque a pessoa pode
# ainda não ter entrado no dashboard nenhuma vez.

def compartilhar_base(dono_id: int, email: str) -> str:
    """Convida um e-mail para a base do dono. Devolve o que houve, em texto."""
    email = (email or "").strip().lower()
    if "@" not in email:
        return "Isso não parece um e-mail."

    criar_schema()
    with conectar() as con:
        dono = con.execute("SELECT email FROM usuarios WHERE id = ?",
                           (int(dono_id),)).fetchone()
        if dono and (dono["email"] or "").strip().lower() == email:
            return "Esse é o seu próprio e-mail — a base já é sua."

        ja = con.execute(
            "SELECT 1 AS existe FROM compartilhamentos WHERE dono_id = ? AND email = ?",
            (int(dono_id), email),
        ).fetchone()
        if ja:
            return f"{email} já tinha acesso."

        con.execute(
            "INSERT INTO compartilhamentos (dono_id, email, criado_em) VALUES (?,?,?)",
            (int(dono_id), email,
             datetime.now(timezone.utc).isoformat(timespec="seconds")),
        )
    return f"{email} agora enxerga e edita esta base."


def descompartilhar_base(dono_id: int, email: str) -> None:
    with conectar() as con:
        con.execute("DELETE FROM compartilhamentos WHERE dono_id = ? AND email = ?",
                    (int(dono_id), (email or "").strip().lower()))


def listar_convidados(dono_id: int) -> list[str]:
    """E-mails que o dono convidou para a base dele."""
    criar_schema()
    with conectar() as con:
        linhas = con.execute(
            "SELECT email FROM compartilhamentos WHERE dono_id = ? ORDER BY email",
            (int(dono_id),),
        ).fetchall()
    return [l["email"] for l in linhas]


def bases_visiveis(usuario_id: int, email: str) -> list[dict]:
    """As bases que esta pessoa pode abrir: a dela e as que lhe deram acesso.

    A primeira da lista é sempre a própria. Cada item traz `id`, `rotulo`
    (o que aparece no seletor) e `propria`.
    """
    criar_schema()
    email = (email or "").strip().lower()
    with conectar() as con:
        eu = con.execute("SELECT nome, email FROM usuarios WHERE id = ?",
                         (int(usuario_id),)).fetchone()
        bases = [{
            "id": int(usuario_id),
            "rotulo": "Minha base",
            "propria": True,
            "dono": (eu["nome"] or eu["email"] or "você") if eu else "você",
        }]
        if not email:
            return bases

        linhas = con.execute(
            "SELECT u.id AS id, u.nome AS nome, u.email AS email "
            "FROM compartilhamentos c JOIN usuarios u ON u.id = c.dono_id "
            "WHERE c.email = ? AND u.id <> ? ORDER BY u.nome, u.email",
            (email, int(usuario_id)),
        ).fetchall()
    for linha in linhas:
        dono = (linha["nome"] or linha["email"] or f"usuário {linha['id']}").strip()
        bases.append({"id": int(linha["id"]), "rotulo": f"Base de {dono}",
                      "propria": False, "dono": dono})
    return bases


def pode_abrir_base(usuario_id: int, email: str, base_id: int) -> bool:
    """Confere o acesso antes de trocar de base — não confia no que veio da tela."""
    return any(b["id"] == int(base_id) for b in bases_visiveis(usuario_id, email))


def _adotar_orfaos(con: Conexao, usuario_id: int) -> None:
    """Entrega ao primeiro usuário tudo que foi gravado antes do login."""
    for tabela in ("lancamentos", "categorias", "orcamentos"):
        con.execute(
            f"UPDATE {tabela} SET usuario_id = ? WHERE usuario_id = ?",
            (usuario_id, USUARIO_ORFAO),
        )


def _semear_categorias(con: Conexao, usuario_id: int) -> None:
    """Dá a um usuário as categorias de fábrica, sem tocar nas que ele criou.

    Chamado a cada login, então vale caber em poucas idas ao banco: uma
    consulta diz o que a pessoa já tem, e só o que falta é inserido — no
    caso comum, o de quem já tem tudo, não há escrita nenhuma.

    Categoria que você apagou de propósito volta no login seguinte. É o
    preço de não guardar uma lista de "apagadas"; renomear resolve melhor.
    """
    ja_tem = {
        l["nome"] for l in con.execute(
            "SELECT nome FROM categorias WHERE usuario_id = ?", (usuario_id,)
        ).fetchall()
    }
    faltando = [padrao for padrao in CATEGORIAS_PADRAO if padrao[0] not in ja_tem]
    if faltando:
        con.executemany(
            "INSERT INTO categorias (usuario_id, nome, tipo, cor, icone) VALUES (?,?,?,?,?)",
            [(usuario_id, *padrao) for padrao in faltando],
        )
    _repintar_cores_padrao(con, usuario_id)


def _repintar_cores_padrao(con: Conexao, usuario_id: int) -> None:
    """Troca a paleta colorida antiga pela rampa neutra atual.

    Só repinta a categoria que ainda está exatamente com a cor antiga de
    fábrica — se você escolheu uma cor no seletor, ela fica como está. Vai
    num `executemany` só: com o banco na nuvem, dezesseis UPDATEs soltos
    seriam dezesseis idas à rede em todo login.
    """
    novas = {nome: cor for nome, _tipo, cor, _icone in CATEGORIAS_PADRAO}
    alvos = []
    for nome, cor_antiga in CORES_ANTIGAS_PADRAO.items():
        nova = novas.get(nome)
        if not nova or nova.lower() == cor_antiga.lower():
            continue
        alvos.append((nova, usuario_id, nome, cor_antiga.lower()))
    if alvos:
        con.executemany(
            "UPDATE categorias SET cor = ? "
            "WHERE usuario_id = ? AND nome = ? AND LOWER(cor) = ?",
            alvos,
        )


# ------------------------------------------------------ categorias

def listar_categorias(tipo: str | None = None) -> pd.DataFrame:
    with conectar() as con:
        df = con.ler_df(
            "SELECT nome, tipo, cor, icone FROM categorias "
            "WHERE usuario_id = ? ORDER BY tipo DESC, nome",
            (_uid(),),
        )
    if tipo:
        df = df[df["tipo"] == tipo].reset_index(drop=True)
    return df


def mapa_cores() -> dict[str, str]:
    df = listar_categorias()
    return dict(zip(df["nome"], df["cor"]))


def mapa_icones() -> dict[str, str]:
    df = listar_categorias()
    return dict(zip(df["nome"], df["icone"]))


def salvar_categoria(nome: str, tipo: str, cor: str, icone: str) -> None:
    with conectar() as con:
        con.execute(
            """INSERT INTO categorias (usuario_id, nome, tipo, cor, icone) VALUES (?,?,?,?,?)
               ON CONFLICT(usuario_id, nome) DO UPDATE SET tipo=excluded.tipo,
                                                           cor=excluded.cor,
                                                           icone=excluded.icone""",
            (_uid(), nome.strip(), tipo, cor, icone),
        )


def excluir_categoria(nome: str) -> int:
    """Remove a categoria. Devolve quantos lançamentos ainda a usam (0 = removida)."""
    usuario_id = _uid()
    with conectar() as con:
        em_uso = con.execute(
            "SELECT COUNT(*) AS n FROM lancamentos WHERE usuario_id = ? AND categoria = ?",
            (usuario_id, nome),
        ).fetchone()["n"]
        if em_uso == 0:
            con.execute(
                "DELETE FROM categorias WHERE usuario_id = ? AND nome = ?",
                (usuario_id, nome),
            )
            con.execute(
                "DELETE FROM orcamentos WHERE usuario_id = ? AND categoria = ?",
                (usuario_id, nome),
            )
    return em_uso


# ------------------------------------------------------ lançamentos

COLUNAS = ["id", "data", "descricao", "categoria", "tipo", "valor", "metodo", "fixo", "obs"]

_SELECT_LANC = ("SELECT id, data, descricao, categoria, tipo, valor, metodo, fixo, obs "
                "FROM lancamentos")


def listar_lancamentos(
    competencia: str | None = None,
    tipos: list[str] | None = None,
    categorias: list[str] | None = None,
    busca: str = "",
) -> pd.DataFrame:
    sql = f"{_SELECT_LANC} WHERE usuario_id = ?"
    params: list = [_uid()]
    if competencia:
        sql += " AND substr(data,1,7) = ?"
        params.append(competencia)
    if tipos:
        sql += f" AND tipo IN ({','.join('?' * len(tipos))})"
        params += tipos
    if categorias:
        sql += f" AND categoria IN ({','.join('?' * len(categorias))})"
        params += categorias
    if busca:
        sql += " AND (LOWER(descricao) LIKE ? OR LOWER(obs) LIKE ?)"
        params += [f"%{busca.lower()}%"] * 2
    sql += " ORDER BY data DESC, id DESC"

    with conectar() as con:
        df = con.ler_df(sql, params)

    if df.empty:
        df = pd.DataFrame(columns=COLUNAS)
        df = df.astype({"id": "Int64", "descricao": "object", "categoria": "object",
                        "tipo": "object", "metodo": "object", "obs": "object"})
    df["data"] = pd.to_datetime(df["data"], errors="coerce")
    df["valor"] = pd.to_numeric(df["valor"], errors="coerce").fillna(0.0)
    df["fixo"] = df["fixo"].astype(bool)
    return df


def inserir_lancamento(data_, descricao, categoria, tipo, valor, metodo="Pix",
                       fixo=False, obs="") -> int:
    with conectar() as con:
        sql = ("""INSERT INTO lancamentos (usuario_id, data, descricao, categoria, tipo, valor, metodo, fixo, obs)
                  VALUES (?,?,?,?,?,?,?,?,?)""")
        if con.postgres:  # no Postgres o id volta pelo RETURNING
            sql += " RETURNING id"
        cur = con.execute(sql, (_uid(), str(data_), descricao.strip(), categoria, tipo,
                                float(valor), metodo, int(bool(fixo)), obs or ""))
        return cur.fetchone()["id"] if con.postgres else cur.lastrowid


def _chave_lancamento(data_, descricao, valor) -> tuple[str, str, float]:
    """Identidade usada para detectar repetição: data + descrição + valor."""
    return (str(data_)[:10], " ".join(str(descricao).lower().split()), round(float(valor), 2))


def chaves_existentes() -> set[tuple[str, str, float]]:
    """Todas as chaves já gravadas — para conferir um lote inteiro de uma vez."""
    with conectar() as con:
        linhas = con.execute(
            "SELECT data, descricao, valor FROM lancamentos WHERE usuario_id = ?",
            (_uid(),),
        ).fetchall()
    return {_chave_lancamento(l["data"], l["descricao"], l["valor"]) for l in linhas}


def lancamento_existe(data_, descricao, valor) -> bool:
    """Confere uma linha só (usado na hora de gravar, contra corridas)."""
    with conectar() as con:
        linhas = con.execute(
            "SELECT data, descricao, valor FROM lancamentos "
            "WHERE usuario_id = ? AND data = ?",
            (_uid(), str(data_)[:10]),
        ).fetchall()
    alvo = _chave_lancamento(data_, descricao, valor)
    return any(_chave_lancamento(l["data"], l["descricao"], l["valor"]) == alvo for l in linhas)


def atualizar_lancamento(id_, data_, descricao, categoria, tipo, valor, metodo,
                         fixo, obs) -> None:
    with conectar() as con:
        con.execute(
            """UPDATE lancamentos SET data=?, descricao=?, categoria=?, tipo=?,
                   valor=?, metodo=?, fixo=?, obs=?
               WHERE id=? AND usuario_id=?""",
            (str(data_), descricao, categoria, tipo, float(valor), metodo,
             int(bool(fixo)), obs or "", int(id_), _uid()),
        )


def excluir_lancamentos(ids: list[int]) -> None:
    if not ids:
        return
    usuario_id = _uid()
    with conectar() as con:
        # o `usuario_id` no WHERE não é decoração: o id vem da tabela da tela,
        # e sem ele um id adivinhado apagaria lançamento de outra pessoa
        con.executemany(
            "DELETE FROM lancamentos WHERE id = ? AND usuario_id = ?",
            [(int(i), usuario_id) for i in ids],
        )


def competencias_disponiveis() -> list[str]:
    with conectar() as con:
        linhas = con.execute(
            "SELECT DISTINCT substr(data,1,7) AS c FROM lancamentos "
            "WHERE usuario_id = ? ORDER BY c DESC",
            (_uid(),),
        ).fetchall()
    meses = [l["c"] for l in linhas if l["c"]]
    atual = date.today().strftime("%Y-%m")
    if atual not in meses:
        meses.insert(0, atual)
    return meses


def repetir_fixos(origem: str, destino: str) -> int:
    """Copia os lançamentos marcados como fixos de um mês para o outro."""
    origem_df = listar_lancamentos(competencia=origem)
    fixos = origem_df[origem_df["fixo"]]
    if fixos.empty:
        return 0

    ja_existem = listar_lancamentos(competencia=destino)
    chaves = set(zip(ja_existem["descricao"], ja_existem["valor"])) if not ja_existem.empty else set()

    ano, mes = map(int, destino.split("-"))
    criados = 0
    for _, linha in fixos.iterrows():
        if (linha["descricao"], linha["valor"]) in chaves:
            continue
        dia = min(linha["data"].day, _ultimo_dia(ano, mes))
        inserir_lancamento(date(ano, mes, dia), linha["descricao"], linha["categoria"],
                           linha["tipo"], linha["valor"], linha["metodo"], True, linha["obs"])
        criados += 1
    return criados


def _ultimo_dia(ano: int, mes: int) -> int:
    proximo = date(ano + (mes == 12), 1 if mes == 12 else mes + 1, 1)
    return (proximo - timedelta(days=1)).day


# -------------------------------------------------------- orçamentos

def listar_orcamentos() -> dict[str, float]:
    with conectar() as con:
        linhas = con.execute(
            "SELECT categoria, limite FROM orcamentos WHERE usuario_id = ?",
            (_uid(),),
        ).fetchall()
    return {l["categoria"]: l["limite"] for l in linhas}


def salvar_orcamento(categoria: str, limite: float) -> None:
    usuario_id = _uid()
    with conectar() as con:
        if limite and limite > 0:
            con.execute(
                """INSERT INTO orcamentos (usuario_id, categoria, limite) VALUES (?,?,?)
                   ON CONFLICT(usuario_id, categoria) DO UPDATE SET limite=excluded.limite""",
                (usuario_id, categoria, float(limite)),
            )
        else:
            con.execute(
                "DELETE FROM orcamentos WHERE usuario_id = ? AND categoria = ?",
                (usuario_id, categoria),
            )


# ------------------------------------------------- importar/exportar

def _ler_data(valor) -> date:
    """Aceita 2026-03-08, 08/03/2026 e variações."""
    texto = str(valor).strip()
    if len(texto) >= 10 and texto[4] == "-":
        return pd.to_datetime(texto[:10], format="%Y-%m-%d").date()
    return pd.to_datetime(texto, dayfirst=True).date()


def importar_dataframe(df: pd.DataFrame) -> tuple[int, list[str]]:
    """Importa um CSV com as colunas data, descricao, categoria, tipo, valor
    (metodo, fixo e obs são opcionais). Devolve (importados, avisos)."""
    obrigatorias = {"data", "descricao", "categoria", "tipo", "valor"}
    faltando = obrigatorias - set(c.lower() for c in df.columns)
    if faltando:
        return 0, [f"Faltam as colunas: {', '.join(sorted(faltando))}"]

    df = df.rename(columns={c: c.lower() for c in df.columns})
    categorias_existentes = set(listar_categorias()["nome"])
    avisos: list[str] = []
    importados = 0

    for i, linha in df.iterrows():
        try:
            data_ = _ler_data(linha["data"])
            tipo = str(linha["tipo"]).strip().lower()
            tipo = "receita" if tipo.startswith("r") else "despesa"
            valor = abs(float(str(linha["valor"]).replace("R$", "").replace(".", "")
                              .replace(",", ".").strip()))
            categoria = str(linha["categoria"]).strip() or "Outros"
            if categoria not in categorias_existentes:
                salvar_categoria(categoria, tipo, "#8A9AAB", "📦")
                categorias_existentes.add(categoria)
            inserir_lancamento(
                data_, str(linha["descricao"]), categoria, tipo, valor,
                str(linha.get("metodo", "Pix")) or "Pix",
                bool(linha.get("fixo", False)),
                str(linha.get("obs", "") or ""),
            )
            importados += 1
        except Exception as erro:  # linha ruim não derruba a importação
            avisos.append(f"Linha {i + 2}: {erro}")

    return importados, avisos


def exportar_csv() -> bytes:
    df = listar_lancamentos()
    if df.empty:
        return "data,descricao,categoria,tipo,valor,metodo,fixo,obs\n".encode("utf-8")
    df = df.copy()
    df["data"] = df["data"].dt.strftime("%Y-%m-%d")
    return df[COLUNAS[1:]].to_csv(index=False).encode("utf-8")


def apagar_tudo() -> None:
    usuario_id = _uid()
    with conectar() as con:
        con.execute("DELETE FROM lancamentos WHERE usuario_id = ?", (usuario_id,))
        con.execute("DELETE FROM orcamentos WHERE usuario_id = ?", (usuario_id,))


# ---------------------------------------------------- dados de teste

_EXEMPLOS = {
    "Moradia": [("Aluguel", 1450, True), ("Condomínio", 380, True), ("Luz", 132, True),
                ("Internet", 99, True), ("Água", 68, True)],
    "Mercado": [("Compra do mês", 520, False), ("Hortifruti", 76, False),
                ("Mercado da esquina", 43, False), ("Padaria", 28, False)],
    "Alimentação": [("Almoço no RU", 18, False), ("iFood", 54, False),
                    ("Café", 12, False), ("Jantar com amigos", 88, False)],
    "Transporte": [("Recarga do bilhete", 120, True), ("Uber", 32, False),
                   ("Gasolina", 180, False)],
    "Assinaturas": [("Spotify", 21.9, True), ("Netflix", 44.9, True),
                    ("GitHub Copilot", 52, True), ("Nuvem 200GB", 9.9, True)],
    "Educação": [("Mensalidade CEUB", 1180, True), ("Livro técnico", 96, False),
                 ("Curso online", 79, False)],
    "Lazer": [("Cinema", 36, False), ("Jogo na Steam", 68, False),
              ("Show", 140, False), ("Bar", 92, False)],
    "Saúde": [("Farmácia", 64, False), ("Academia", 109, True)],
    "Compras": [("Camiseta", 89, False), ("Fone de ouvido", 199, False),
                ("Cabo USB-C", 39, False)],
    "Investimentos": [("Aporte Tesouro Selic", 400, True)],
}


def popular_exemplo(meses: int = 6) -> int:
    """Gera alguns meses de lançamentos plausíveis para você ver o dashboard cheio."""
    random.seed(7)
    hoje = date.today()
    criados = 0

    for volta in range(meses - 1, -1, -1):
        ano = hoje.year
        mes = hoje.month - volta
        while mes <= 0:
            mes += 12
            ano -= 1
        ultimo = _ultimo_dia(ano, mes)
        limite_dia = hoje.day if (ano, mes) == (hoje.year, hoje.month) else ultimo

        inserir_lancamento(date(ano, mes, min(5, limite_dia)), "Salário", "Salário",
                           "receita", 4200, "Transferência", True)
        criados += 1
        if random.random() < 0.6:
            dia = random.randint(1, limite_dia)
            inserir_lancamento(date(ano, mes, dia), "Projeto freelance", "Freelance",
                               "receita", random.choice([600, 900, 1250]), "Pix")
            criados += 1

        for categoria, itens in _EXEMPLOS.items():
            for descricao, valor, fixo in itens:
                if not fixo and random.random() < 0.35:
                    continue
                repeticoes = 1 if fixo else random.randint(1, 3)
                for _ in range(repeticoes):
                    dia = random.randint(1, limite_dia)
                    variacao = 1 if fixo else random.uniform(0.7, 1.4)
                    inserir_lancamento(
                        date(ano, mes, dia), descricao, categoria, "despesa",
                        round(valor * variacao, 2),
                        random.choice(["Pix", "Crédito", "Débito"]), fixo,
                    )
                    criados += 1

    for categoria, limite in [("Moradia", 2200), ("Mercado", 800), ("Alimentação", 400),
                              ("Transporte", 350), ("Lazer", 300), ("Assinaturas", 150),
                              ("Educação", 1300), ("Compras", 250)]:
        salvar_orcamento(categoria, limite)

    return criados
