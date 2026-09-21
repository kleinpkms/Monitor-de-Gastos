"""
Leitura de faturas de cartão de crédito em PDF.

Cada página é lida de duas formas e vence a que achar mais transações:

1. `page.extract_tables()` — faturas costumam vir em tabela, e aí cada
   célula já chega separada (data | descrição | valor);
2. `page.extract_text()` + varredura por regex, para faturas em texto corrido.

O resultado sai pré-classificado pelas palavras-chave de
`config.PALAVRAS_CHAVE_CATEGORIA`; o que não casa com nenhuma vira
"Não atribuído" em vez de ser descartado. Nada é gravado aqui — o app
mostra a tabela para revisão e só então chama `database.inserir_lancamento`.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, timedelta

import pandas as pd

import database as db
from config import (CATEGORIA_NAO_ATRIBUIDA, LINHAS_IGNORADAS_EXTRATO,
                    PALAVRAS_CHAVE_CATEGORIA, PALAVRAS_IGNORADAS_EXTRATO)

COLUNAS_EXTRATO = ["importar", "data", "descricao", "categoria", "tipo", "valor", "situacao"]

MESES_ABREV = {
    "jan": 1, "fev": 2, "mar": 3, "abr": 4, "mai": 5, "jun": 6,
    "jul": 7, "ago": 8, "set": 9, "out": 10, "nov": 11, "dez": 12,
}

# "05/03", "05/03/26", "05.03.2026", "05-03" ou "05 MAR"
RE_DATA = re.compile(
    r"\b(\d{1,2}\s*[/.\-]\s*\d{1,2}(?:\s*[/.\-]\s*\d{2,4})?"
    r"|\d{1,2}\s+(?:jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez)[a-z]*\.?)",
    re.IGNORECASE,
)

# "32,90", "R$ 1.234,56", "-44,90", "44,90-", "(44,90)" — milhar opcional
RE_VALOR = re.compile(
    r"(?<![\d./-])"
    r"(?P<antes>[-(]\s*)?"
    r"(?:R\$\s*)?"
    r"(?P<numero>\d{1,3}(?:\.\d{3})+,\d{2}|\d+,\d{2})"
    r"(?P<depois>\s*[-)])?"
    r"(?![\d,])"
)

# uma data sozinha (para reconhecer a célula de data dentro de uma tabela)
RE_SO_DATA = re.compile(rf"^{RE_DATA.pattern}$", re.IGNORECASE)

# ------------------------------------------------------- padrão Banco Inter
# "17 de ago. 2026 PAGTO DEBITO AUTOMATICO - + R$ 1.327,68"
# "21 de ago. 2026 PertoEPronto - R$ 12,98"
# O "+" antes do R$ marca pagamento/estorno — não é despesa.
RE_LINHA_INTER = re.compile(
    r"^(?P<dia>\d{1,2})\s+de\s+"
    r"(?P<mes>jan|fev|mar|abr|mai|jun|jul|ago|set|out|nov|dez)\.?\s*"
    r"(?P<ano>\d{4})?\s+"
    r"(?P<desc>.+?)\s+-\s+"
    r"(?P<mais>\+\s*)?R\$\s*"
    r"(?P<valor>\d{1,3}(?:\.\d{3})*,\d{2}|\d+,\d{2})\s*$",
    re.IGNORECASE,
)

# Cabeçalho de seção: "CARTÃO 5364 **** **** 1234" — cada cartão é uma seção.
# O ".{0,6}" no lugar do "Ã" é proposital: quando o PDF não traz mapa Unicode
# da fonte, o acento sai como lixo ("CARTˆO", "CART(cid:195)O").
RE_CARTAO_INTER = re.compile(r"^cart.{0,6}o\b\s*(?P<id>.*)$")

# começos de linha que nunca são lançamento (lançamento começa com dígito)
PREFIXOS_IGNORADOS_INTER = (
    "total", "data movimenta", "cart", "limite", "vencimento", "saldo",
    "fatura", "resumo", "pagamento minimo", "valor total", "encargos",
    "juros", "lancamentos", "descricao", "banco inter",
)

# do primeiro destes marcadores em diante, o PDF fala do futuro — descartar
MARCAS_FIM_INTER = tuple(re.compile(padrao) for padrao in (
    r"pr.{0,6}xima\s+fatura",
    r"pr.{0,6}ximas\s+faturas",
    r"parcelamentos?\s+futur",
    r"compras\s+parceladas\s+futuras",
    r"lancamentos\s+futuros",
    r"faturas?\s+futuras?",
))


# Caractere que o pdfplumber não soube traduzir (fonte sem mapa Unicode):
# "Pr(cid:243)xima fatura", "CAF(cid:201) EXPRESSO".
RE_CID = re.compile(r"\(cid:\d+\)")


def normalizar(texto: str) -> str:
    """Minúsculas, sem acento, sem lixo de fonte e com espaços colapsados."""
    limpo = RE_CID.sub("", str(texto))
    sem_acento = unicodedata.normalize("NFKD", limpo)
    sem_acento = "".join(c for c in sem_acento if not unicodedata.combining(c))
    return " ".join(sem_acento.lower().split())


# --------------------------------------------------------------- resultado

@dataclass
class Leitura:
    """Tudo que a leitura de um PDF produziu — inclusive material de depuração."""

    transacoes: pd.DataFrame
    paginas: list[str] = field(default_factory=list)   # texto bruto por página
    metodo: str = "nenhum"                  # inter | tabelas | texto | nenhum
    diagnostico: list[str] = field(default_factory=list)
    pagamentos_ignorados: int = 0           # linhas "+ R$" (pagamento/estorno)
    cortou_futuro: bool = False             # achou "Próxima fatura" e cortou ali

    @property
    def texto(self) -> str:
        return "\n".join(self.paginas)


# ------------------------------------------------------------- abrir o PDF

def _erro_de_senha(erro: BaseException) -> bool:
    """O pdfplumber embrulha o erro do pdfminer, então olhamos a cadeia toda."""
    vistos: list[BaseException] = []
    atual: BaseException | None = erro
    while atual is not None and atual not in vistos:
        vistos.append(atual)
        pistas = f"{type(atual).__name__} {atual} {atual.args}".lower()
        if "password" in pistas or "encrypt" in pistas:
            return True
        atual = atual.__cause__ or atual.__context__
    return False


def abrir_pdf(arquivo, senha: str = ""):
    """Abre o PDF (com senha, se a fatura vier protegida)."""
    try:
        import pdfplumber
    except ImportError as erro:  # dependência opcional até o primeiro uso
        raise RuntimeError(
            "A leitura de PDF precisa do pdfplumber. Rode: pip install pdfplumber"
        ) from erro

    try:
        return pdfplumber.open(arquivo, password=senha or "")
    except Exception as erro:
        if _erro_de_senha(erro):
            raise RuntimeError(
                "A fatura está protegida e a senha informada não abriu o arquivo."
                if senha else
                "A fatura está protegida por senha. Preencha o campo Senha do PDF."
            ) from erro
        raise


def extrair_texto(arquivo, senha: str = "") -> str:
    """Texto de todas as páginas — atalho para quem só quer o texto bruto."""
    with abrir_pdf(arquivo, senha) as pdf:
        return "\n".join((pagina.extract_text() or "") for pagina in pdf.pages)


# ------------------------------------------------------------ peças da linha

def _ler_valor(bruto: str) -> float | None:
    """'R$ 1.234,56' -> 1234.56 · '(44,90)' e '44,90-' -> -44.90."""
    casou = RE_VALOR.search(str(bruto))
    if not casou:
        return None
    numero = casou.group("numero").replace(".", "").replace(",", ".")
    try:
        valor = float(numero)
    except ValueError:
        return None
    negativo = bool(casou.group("antes")) or bool(casou.group("depois"))
    return -valor if negativo else valor


def _ler_data(bruto: str, ano_ref: int) -> date | None:
    texto = normalizar(bruto).replace(".", "/").replace("-", "/")
    texto = re.sub(r"\s*/\s*", "/", texto)

    if "/" in texto:
        partes = [p for p in texto.split("/") if p]
        if len(partes) < 2 or not partes[0].isdigit() or not partes[1].isdigit():
            return None
        dia, mes = int(partes[0]), int(partes[1])
        ano = ano_ref
        if len(partes) > 2 and partes[2].isdigit():
            ano = int(partes[2])
            ano += 2000 if ano < 100 else 0
    else:
        partes = texto.split()
        if len(partes) < 2 or not partes[0].isdigit():
            return None
        mes_txt = partes[1][:3]
        if mes_txt not in MESES_ABREV:
            return None
        dia, mes, ano = int(partes[0]), MESES_ABREV[mes_txt], ano_ref

    try:
        data_ = date(ano, mes, dia)
    except ValueError:
        return None

    # fatura de dezembro aberta em janeiro: sem o ano no PDF, volta um ano
    if data_ > date.today() + timedelta(days=45):
        try:
            data_ = data_.replace(year=data_.year - 1)
        except ValueError:
            return None
    return data_


def _limpar_descricao(bruto: str) -> str:
    texto = " ".join(RE_CID.sub("", str(bruto)).split())
    texto = re.sub(r"\s*R\$\s*$", "", texto)
    texto = texto.strip(" .-·|*;:,")
    if texto and texto == texto.upper():
        texto = texto.title()
    return texto


def _tem_letras(texto: str, minimo: int = 3) -> bool:
    return len(re.findall(r"[A-Za-zÀ-ÿ]", str(texto))) >= minimo


def categoria_sugerida(descricao: str) -> str:
    """Primeira categoria cuja palavra-chave aparece na descrição.

    Palavras maiores têm prioridade, então "mercado livre" ganha de "mercado".
    Sem nenhuma correspondência devolve a categoria de não atribuídos — a
    transação entra assim mesmo, para você classificar na revisão.
    """
    alvo = normalizar(descricao)
    melhor_categoria, melhor_tamanho = CATEGORIA_NAO_ATRIBUIDA, 0
    for categoria, palavras in PALAVRAS_CHAVE_CATEGORIA.items():
        for palavra in palavras:
            chave = normalizar(palavra)
            if chave and chave in alvo and len(chave) > melhor_tamanho:
                melhor_categoria, melhor_tamanho = categoria, len(chave)
    return melhor_categoria


def linha_ignorada(linha: str) -> bool:
    """Cabeçalho, rodapé, total, limite… — não é lançamento."""
    alvo = normalizar(linha)
    if any(normalizar(trecho) in alvo for trecho in LINHAS_IGNORADAS_EXTRATO):
        return True
    palavras = set(re.findall(r"[a-z0-9]+", alvo))
    return any(normalizar(p) in palavras for p in PALAVRAS_IGNORADAS_EXTRATO)


def _montar(data_, descricao: str, valor: float, nota: str = "") -> dict:
    """Transação já classificada. Valor negativo em fatura é estorno/crédito."""
    tipo = "receita" if valor < 0 else "despesa"
    return {
        "data": data_,
        "descricao": descricao,
        "categoria": categoria_sugerida(descricao) if tipo == "despesa"
                     else CATEGORIA_NAO_ATRIBUIDA,
        "tipo": tipo,
        "valor": abs(valor),
        "nota": nota,
    }


# ------------------------------------------------------ varredura por linha

def transacoes_da_linha(linha: str, ano_ref: int,
                        data_anterior: date | None = None) -> list[dict]:
    """Extrai as transações de UMA linha de texto.

    Percorre datas e valores na ordem em que aparecem e vai fechando blocos:
    uma data só começa bloco novo depois que o bloco atual já tem valor. Assim
    "LOJA X PARC 02/10 39,90" continua sendo uma transação só (o 02/10 fica na
    descrição) e "05/03 UBER 32,90 06/03 IFOOD 54,00" vira duas. Quando o bloco
    recebe mais de um valor (compra internacional traz dólar e real), vale o
    último — o valor em real.
    """
    linha = " ".join(str(linha).replace("\xa0", " ").split())
    if len(linha) < 5 or linha_ignorada(linha):
        return []

    marcas = [("data", m) for m in RE_DATA.finditer(linha)]
    marcas += [("valor", m) for m in RE_VALOR.finditer(linha)]
    marcas.sort(key=lambda par: par[1].start())
    if not any(tipo == "valor" for tipo, _ in marcas):
        return []

    blocos: list[dict] = []
    atual: dict | None = None
    for tipo, marca in marcas:
        if tipo == "data":
            if atual is None or atual["valor"] is not None:
                atual = {"data": marca, "valor": None, "fim_data": marca.end(),
                         "inicio_valor": None}
                blocos.append(atual)
        else:
            if atual is None:  # valor antes de qualquer data
                atual = {"data": None, "valor": marca, "fim_data": 0,
                         "inicio_valor": marca.start()}
                blocos.append(atual)
            elif atual["inicio_valor"] is None:
                atual["inicio_valor"] = marca.start()
                atual["valor"] = marca
            else:
                atual["valor"] = marca  # o último valor do bloco é o que vale

    achados: list[dict] = []
    for i, bloco in enumerate(blocos):
        if bloco["valor"] is None:
            continue
        proximo = blocos[i + 1]["data"] if i + 1 < len(blocos) else None
        fim = proximo.start() if proximo is not None else len(linha)
        descricao = _limpar_descricao(linha[bloco["fim_data"]:bloco["inicio_valor"]])
        if not _tem_letras(descricao):  # descrição vem depois do valor
            descricao = _limpar_descricao(linha[bloco["valor"].end():fim])
        valor = _ler_valor(bloco["valor"].group(0))
        if valor is None or valor == 0 or not _tem_letras(descricao):
            continue

        nota = ""
        if bloco["data"] is not None:
            data_ = _ler_data(bloco["data"].group(0), ano_ref)
        else:
            # linha sem data: a fatura repete a data só na primeira linha do dia
            data_, nota = data_anterior, "Data presumida"
        if data_ is None:
            continue
        achados.append(_montar(data_, descricao, valor, nota))

    return achados


# ------------------------------------------------------- padrão Banco Inter

def cortar_fatura_futura(texto: str) -> tuple[str, bool]:
    """Devolve o texto até "Próxima fatura" — dali em diante é compra futura."""
    linhas = str(texto).splitlines()
    for i, linha in enumerate(linhas):
        alvo = normalizar(linha)
        if any(marca.search(alvo) for marca in MARCAS_FIM_INTER):
            return "\n".join(linhas[:i]), True
    return texto, False


def parsear_inter(texto: str, ano_ref: int | None = None) -> tuple[pd.DataFrame, int]:
    """Lê a fatura do Banco Inter: "17 de ago. 2026 DESCRIÇÃO - R$ 12,98".

    O ano vem na própria linha; o "Ano da fatura" da tela só entra se a linha
    não trouxer um. Linhas com "+" antes do R$ são pagamento/estorno e são
    puladas (a contagem volta junto, para o app avisar). Cada "CARTÃO ****"
    abre uma seção nova e todas são lidas, sem repetir a mesma transação.
    Devolve (transações, quantas linhas de pagamento foram puladas).
    """
    ano_ref = ano_ref or date.today().year
    achados: list[dict] = []
    vistos: set[tuple] = set()
    pagamentos = 0
    cartao = ""

    for linha_bruta in str(texto).splitlines():
        linha = " ".join(linha_bruta.replace("\xa0", " ").split())
        if not linha:
            continue

        alvo = normalizar(linha)
        cabecalho = RE_CARTAO_INTER.match(alvo)
        if cabecalho:  # "CARTÃO 5364 **** **** 1234" — troca de seção
            cartao = cabecalho.group("id") or cartao
            continue
        if alvo.startswith(PREFIXOS_IGNORADOS_INTER):
            continue

        casou = RE_LINHA_INTER.match(linha)
        if not casou:
            continue

        if casou.group("mais"):  # "+ R$" = pagamento da fatura ou estorno
            pagamentos += 1
            continue

        mes = MESES_ABREV.get(casou.group("mes").lower())
        if mes is None:
            continue
        try:
            data_ = date(int(casou.group("ano") or ano_ref), mes, int(casou.group("dia")))
        except ValueError:
            continue

        valor = float(casou.group("valor").replace(".", "").replace(",", "."))
        descricao = _limpar_descricao(casou.group("desc"))
        if valor <= 0 or not _tem_letras(descricao):
            continue

        chave = (cartao, data_, normalizar(descricao), round(valor, 2))
        if chave in vistos:  # mesma linha repetida dentro da seção
            continue
        vistos.add(chave)
        achados.append(_montar(data_, descricao, valor))

    return _como_dataframe(achados), pagamentos


# ------------------------------------------------------- padrões genéricos

def parsear_texto(texto: str, ano_ref: int | None = None) -> pd.DataFrame:
    """Varre o texto inteiro da fatura, linha a linha."""
    ano_ref = ano_ref or date.today().year
    achados: list[dict] = []
    ultima_data: date | None = None

    for linha in str(texto).splitlines():
        for transacao in transacoes_da_linha(linha, ano_ref, ultima_data):
            if not transacao["nota"]:
                ultima_data = transacao["data"]
            achados.append(transacao)

    return _como_dataframe(achados)


# --------------------------------------------------- varredura em tabela

def transacoes_da_tabela(tabela, ano_ref: int) -> list[dict]:
    """Extrai as transações de uma tabela devolvida por `extract_tables()`."""
    achados: list[dict] = []
    ultima_data: date | None = None

    for linha in tabela or []:
        celulas = [" ".join(str(c or "").split()) for c in linha]
        texto_linha = " ".join(c for c in celulas if c)
        if not texto_linha or linha_ignorada(texto_linha):
            continue

        # a célula que é só uma data, e a última célula que é um valor
        idx_data = next(
            (i for i, c in enumerate(celulas)
             if c and RE_SO_DATA.match(c) and _ler_data(c, ano_ref)),
            None,
        )
        idx_valor = next(
            (i for i in range(len(celulas) - 1, -1, -1)
             if celulas[i] and _ler_valor(celulas[i]) is not None
             and not _tem_letras(celulas[i], 4)),
            None,
        )

        novos: list[dict] = []
        if idx_data is not None and idx_valor is not None and idx_data != idx_valor:
            descricao = _limpar_descricao(" ".join(
                c for i, c in enumerate(celulas)
                if i not in (idx_data, idx_valor) and _tem_letras(c, 2)
            ))
            valor = _ler_valor(celulas[idx_valor])
            data_ = _ler_data(celulas[idx_data], ano_ref)
            if data_ is not None and valor not in (None, 0) and _tem_letras(descricao):
                novos = [_montar(data_, descricao, valor)]

        if not novos:
            # tabela mal formada, ou a linha inteira numa célula só
            novos = transacoes_da_linha(texto_linha, ano_ref, ultima_data)

        for transacao in novos:
            if not transacao["nota"]:
                ultima_data = transacao["data"]
            achados.append(transacao)

    return achados


# ---------------------------------------------------------------- juntando

def _como_dataframe(achados: list[dict]) -> pd.DataFrame:
    colunas = ["data", "descricao", "categoria", "tipo", "valor", "nota"]
    df = pd.DataFrame(achados, columns=colunas)
    if df.empty:
        return df
    return df.sort_values("data", kind="stable").reset_index(drop=True)


def marcar_duplicados(df: pd.DataFrame) -> pd.DataFrame:
    """Acrescenta as colunas de controle e desmarca o que já está na base."""
    if df.empty:
        return pd.DataFrame(columns=COLUNAS_EXTRATO)

    existentes = db.chaves_existentes()
    df = df.copy()
    if "nota" not in df.columns:
        df["nota"] = ""
    situacoes, importar = [], []
    for _, linha in df.iterrows():
        chave = db._chave_lancamento(linha["data"], linha["descricao"], linha["valor"])
        duplicado = chave in existentes
        situacoes.append("Já existe na base" if duplicado else (linha["nota"] or "Novo"))
        importar.append(not duplicado)
    df["situacao"] = situacoes
    df["importar"] = importar
    return df[COLUNAS_EXTRATO]


def ler_fatura(arquivo, ano_ref: int | None = None, senha: str = "") -> Leitura:
    """PDF -> tabela pronta para revisão, mais o material de depuração."""
    ano_ref = ano_ref or date.today().year
    paginas: list[str] = []
    por_tabela: list[dict] = []
    total_tabelas = 0

    with abrir_pdf(arquivo, senha) as pdf:
        for pagina in pdf.pages:
            paginas.append(pagina.extract_text() or "")
            try:
                tabelas = pagina.extract_tables() or []
            except Exception:  # página sem grade reconhecível
                tabelas = []
            total_tabelas += len(tabelas)
            for tabela in tabelas:
                por_tabela += transacoes_da_tabela(tabela, ano_ref)

    texto_completo = "\n".join(paginas)
    texto, cortou = cortar_fatura_futura(texto_completo)

    df_inter, pagamentos = parsear_inter(texto, ano_ref)
    df_tabela = _como_dataframe(por_tabela)
    df_texto = parsear_texto(texto, ano_ref)

    # o padrão do Inter manda; tabela e varredura genérica são rede de segurança
    if not df_inter.empty:
        escolhido, metodo = df_inter, "padrão Inter"
    elif not df_tabela.empty:
        escolhido, metodo = df_tabela, "tabelas"
    elif not df_texto.empty:
        escolhido, metodo = df_texto, "texto"
    else:
        escolhido, metodo = df_inter, "nenhum"

    caracteres = len(texto_completo.strip())
    diagnostico = [
        f"{len(paginas)} página(s), {caracteres} caractere(s) de texto extraído",
        f"padrão Inter (dia de mês. ano … - R$) → {len(df_inter)} transação(ões)",
        f"{total_tabelas} tabela(s) detectada(s) → {len(df_tabela)} transação(ões)",
        f"varredura genérica do texto → {len(df_texto)} transação(ões)",
        f"método escolhido: {metodo}",
    ]
    if pagamentos:
        diagnostico.append(
            f"{pagamentos} linha(s) com \"+ R$\" (pagamento/estorno) puladas — "
            "não são despesa"
        )
    if cortou:
        diagnostico.append(
            "Achei \"Próxima fatura\": tudo dali em diante (compras futuras e "
            "parcelas a vencer) foi descartado"
        )
    if caracteres == 0:
        diagnostico.append(
            "Nenhum texto no PDF: a fatura provavelmente é digitalizada (imagem), "
            "e aí só com OCR."
        )

    return Leitura(marcar_duplicados(escolhido), paginas, metodo, diagnostico,
                   pagamentos, cortou)
