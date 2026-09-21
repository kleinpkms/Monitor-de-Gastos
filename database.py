"""
Camada de dados do dashboard. Tudo fica em um único arquivo SQLite
(`financas.db`) criado ao lado do projeto — é só copiar esse arquivo
para levar seus dados para outra máquina.
"""

from __future__ import annotations

import os
import random
import sqlite3
from datetime import date, timedelta

import pandas as pd

from config import (CATEGORIA_NAO_ATRIBUIDA, CATEGORIAS_PADRAO,
                    CORES_ANTIGAS_PADRAO)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get("FINANCAS_DB", os.path.join(BASE_DIR, "financas.db"))


# --------------------------------------------------------- conexão

def conectar() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def criar_schema() -> None:
    with conectar() as con:
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS categorias (
                nome  TEXT PRIMARY KEY,
                tipo  TEXT NOT NULL CHECK (tipo IN ('despesa','receita')),
                cor   TEXT NOT NULL DEFAULT '#8A9AAB',
                icone TEXT NOT NULL DEFAULT '📦'
            );

            CREATE TABLE IF NOT EXISTS lancamentos (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                data      TEXT NOT NULL,
                descricao TEXT NOT NULL,
                categoria TEXT NOT NULL,
                tipo      TEXT NOT NULL CHECK (tipo IN ('despesa','receita')),
                valor     REAL NOT NULL,
                metodo    TEXT DEFAULT 'Pix',
                fixo      INTEGER NOT NULL DEFAULT 0,
                obs       TEXT DEFAULT ''
            );

            CREATE INDEX IF NOT EXISTS idx_lanc_data ON lancamentos(data);

            CREATE TABLE IF NOT EXISTS orcamentos (
                categoria TEXT PRIMARY KEY,
                limite    REAL NOT NULL
            );
            """
        )
        cur = con.execute("SELECT COUNT(*) AS n FROM categorias")
        if cur.fetchone()["n"] == 0:
            con.executemany(
                "INSERT INTO categorias (nome, tipo, cor, icone) VALUES (?,?,?,?)",
                CATEGORIAS_PADRAO,
            )
        # bases criadas antes da importação de extrato podem não ter a categoria
        con.execute(
            "INSERT OR IGNORE INTO categorias (nome, tipo, cor, icone) VALUES (?,?,?,?)",
            (CATEGORIA_NAO_ATRIBUIDA, "despesa", "#49525F", "❓"),
        )
        _repintar_cores_padrao(con)


def _repintar_cores_padrao(con: sqlite3.Connection) -> None:
    """Troca a paleta colorida antiga pela rampa neutra atual.

    Só repinta a categoria que ainda está exatamente com a cor antiga de
    fábrica — se você escolheu uma cor no seletor, ela fica como está.
    """
    novas = {nome: cor for nome, _tipo, cor, _icone in CATEGORIAS_PADRAO}
    for nome, cor_antiga in CORES_ANTIGAS_PADRAO.items():
        nova = novas.get(nome)
        if not nova or nova.lower() == cor_antiga.lower():
            continue
        con.execute(
            "UPDATE categorias SET cor = ? WHERE nome = ? AND LOWER(cor) = ?",
            (nova, nome, cor_antiga.lower()),
        )


# ------------------------------------------------------ categorias

def listar_categorias(tipo: str | None = None) -> pd.DataFrame:
    with conectar() as con:
        df = pd.read_sql_query("SELECT * FROM categorias ORDER BY tipo DESC, nome", con)
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
            """INSERT INTO categorias (nome, tipo, cor, icone) VALUES (?,?,?,?)
               ON CONFLICT(nome) DO UPDATE SET tipo=excluded.tipo,
                                               cor=excluded.cor,
                                               icone=excluded.icone""",
            (nome.strip(), tipo, cor, icone),
        )


def excluir_categoria(nome: str) -> int:
    """Remove a categoria. Devolve quantos lançamentos ainda a usam (0 = removida)."""
    with conectar() as con:
        em_uso = con.execute(
            "SELECT COUNT(*) AS n FROM lancamentos WHERE categoria = ?", (nome,)
        ).fetchone()["n"]
        if em_uso == 0:
            con.execute("DELETE FROM categorias WHERE nome = ?", (nome,))
            con.execute("DELETE FROM orcamentos WHERE categoria = ?", (nome,))
    return em_uso


# ------------------------------------------------------ lançamentos

COLUNAS = ["id", "data", "descricao", "categoria", "tipo", "valor", "metodo", "fixo", "obs"]


def listar_lancamentos(
    competencia: str | None = None,
    tipos: list[str] | None = None,
    categorias: list[str] | None = None,
    busca: str = "",
) -> pd.DataFrame:
    sql = "SELECT * FROM lancamentos WHERE 1=1"
    params: list = []
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
        df = pd.read_sql_query(sql, con, params=params)

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
        cur = con.execute(
            """INSERT INTO lancamentos (data, descricao, categoria, tipo, valor, metodo, fixo, obs)
               VALUES (?,?,?,?,?,?,?,?)""",
            (str(data_), descricao.strip(), categoria, tipo, float(valor),
             metodo, int(bool(fixo)), obs or ""),
        )
        return cur.lastrowid


def _chave_lancamento(data_, descricao, valor) -> tuple[str, str, float]:
    """Identidade usada para detectar repetição: data + descrição + valor."""
    return (str(data_)[:10], " ".join(str(descricao).lower().split()), round(float(valor), 2))


def chaves_existentes() -> set[tuple[str, str, float]]:
    """Todas as chaves já gravadas — para conferir um lote inteiro de uma vez."""
    with conectar() as con:
        linhas = con.execute("SELECT data, descricao, valor FROM lancamentos").fetchall()
    return {_chave_lancamento(l["data"], l["descricao"], l["valor"]) for l in linhas}


def lancamento_existe(data_, descricao, valor) -> bool:
    """Confere uma linha só (usado na hora de gravar, contra corridas)."""
    with conectar() as con:
        linhas = con.execute(
            "SELECT data, descricao, valor FROM lancamentos WHERE data = ?",
            (str(data_)[:10],),
        ).fetchall()
    alvo = _chave_lancamento(data_, descricao, valor)
    return any(_chave_lancamento(l["data"], l["descricao"], l["valor"]) == alvo for l in linhas)


def atualizar_lancamento(id_, data_, descricao, categoria, tipo, valor, metodo,
                         fixo, obs) -> None:
    with conectar() as con:
        con.execute(
            """UPDATE lancamentos SET data=?, descricao=?, categoria=?, tipo=?,
                   valor=?, metodo=?, fixo=?, obs=? WHERE id=?""",
            (str(data_), descricao, categoria, tipo, float(valor), metodo,
             int(bool(fixo)), obs or "", int(id_)),
        )


def excluir_lancamentos(ids: list[int]) -> None:
    if not ids:
        return
    with conectar() as con:
        con.executemany("DELETE FROM lancamentos WHERE id = ?", [(int(i),) for i in ids])


def competencias_disponiveis() -> list[str]:
    with conectar() as con:
        linhas = con.execute(
            "SELECT DISTINCT substr(data,1,7) AS c FROM lancamentos ORDER BY c DESC"
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
        linhas = con.execute("SELECT categoria, limite FROM orcamentos").fetchall()
    return {l["categoria"]: l["limite"] for l in linhas}


def salvar_orcamento(categoria: str, limite: float) -> None:
    with conectar() as con:
        if limite and limite > 0:
            con.execute(
                """INSERT INTO orcamentos (categoria, limite) VALUES (?,?)
                   ON CONFLICT(categoria) DO UPDATE SET limite=excluded.limite""",
                (categoria, float(limite)),
            )
        else:
            con.execute("DELETE FROM orcamentos WHERE categoria = ?", (categoria,))


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
    with conectar() as con:
        con.execute("DELETE FROM lancamentos")
        con.execute("DELETE FROM orcamentos")


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
