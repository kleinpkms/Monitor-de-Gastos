"""
Configuração central do dashboard: paleta, tipografia, categorias e
template dos gráficos.

Paleta minimalista: três neutros (fundo, texto, texto fraco) mais um
acento verde. O acento marca só o que é positivo — entradas e saldo
sobrando; o que sai fica no ramo neutro, e as categorias são uma rampa
de cinzas ordenada, o que dispensa decorar legenda de cor.
"""

from __future__ import annotations

import os

# ---------------------------------------------------------------- tema

TEMA = {
    # --- neutros
    "fundo": "#0F1216",
    "superficie": "#161A20",
    "superficie_alt": "#1D222A",
    "linha": "#21262E",        # hairline
    "texto": "#E9ECEF",
    "texto_fraco": "#8C929B",
    # --- único acento: o que é positivo
    "entrada": "#4CC38A",
    # o que sai / alerta / séries de apoio ficam no ramo neutro
    "saida": "#B9BFC7",
    "atencao": "#E9ECEF",
    "destaque": "#C9CED6",
}

# Uma família só, dois pesos (400 no corpo, 600 em título e número).
FONTE_UI = "Inter"
FONTE_NUMERO = "Inter"

# --------------------------------------------------------- categorias
# (nome, tipo, cor, ícone)
CATEGORIAS_PADRAO = [
    ("Moradia", "despesa", "#E4E8EC", "🏠"),
    ("Mercado", "despesa", "#D6DBE1", "🛒"),
    ("Alimentação", "despesa", "#C8CED6", "🍽️"),
    ("Transporte", "despesa", "#BAC1CA", "🚌"),
    ("Saúde", "despesa", "#ACB4BF", "💊"),
    ("Educação", "despesa", "#9EA7B3", "📚"),
    ("Lazer", "despesa", "#909AA8", "🎬"),
    ("Assinaturas", "despesa", "#828D9C", "📺"),
    ("Compras", "despesa", "#748090", "👕"),
    ("Investimentos", "despesa", "#667385", "📈"),
    ("Outros", "despesa", "#586679", "📦"),
    ("Não atribuído", "despesa", "#49525F", "❓"),
    ("Salário", "receita", "#4CC38A", "💼"),
    ("Freelance", "receita", "#6FCFA0", "💻"),
    ("Rendimentos", "receita", "#92DBB7", "🏦"),
    ("Outras entradas", "receita", "#B5E7CD", "✨"),
]

# Cores da paleta antiga (colorida). A migração em database.py só repinta
# categorias que ainda estão com um destes valores — cor escolhida a mão
# pelo usuário no seletor de cor é preservada.
CORES_ANTIGAS_PADRAO = {
    "Moradia": "#7C6BD6", "Mercado": "#5FA85A", "Alimentação": "#E08A3C",
    "Transporte": "#4AA3B8", "Saúde": "#D95B7F", "Educação": "#8F7AC4",
    "Lazer": "#E0603C", "Assinaturas": "#3FA8A0", "Compras": "#C7A24B",
    "Investimentos": "#3FBF7F", "Outros": "#8A9AAB", "Não atribuído": "#6B7785",
    "Salário": "#3FBF7F", "Freelance": "#5BD3A0", "Rendimentos": "#79C9E8",
    "Outras entradas": "#A8D98A",
}

METODOS = ["Pix", "Débito", "Crédito", "Dinheiro", "Boleto", "Transferência"]

TIPOS = ["despesa", "receita"]

MESES_PT = [
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
]


def nome_competencia(competencia: str) -> str:
    """'2026-03' -> 'março de 2026'."""
    ano, mes = competencia.split("-")
    return f"{MESES_PT[int(mes) - 1]} de {ano}"


def rotulo_curto(competencia: str) -> str:
    """'2026-03' -> 'mar/26'."""
    ano, mes = competencia.split("-")
    return f"{MESES_PT[int(mes) - 1][:3]}/{ano[2:]}"


# ------------------------------------------------------ plotly layout

def layout_base(altura: int = 320, margem: dict | None = None) -> dict:
    """Layout compartilhado por todos os gráficos."""
    return dict(
        height=altura,
        margin=margem or dict(l=8, r=8, t=8, b=8),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=f"{FONTE_UI}, sans-serif", size=13, color=TEMA["texto_fraco"]),
        hoverlabel=dict(
            bgcolor=TEMA["superficie_alt"],
            bordercolor=TEMA["linha"],
            font=dict(family=f"{FONTE_UI}, sans-serif", size=13, color=TEMA["texto"]),
        ),
        xaxis=dict(showgrid=False, zeroline=False, linecolor=TEMA["linha"], ticks="outside",
                   tickcolor=TEMA["linha"], ticklen=4),
        yaxis=dict(gridcolor=TEMA["linha"], griddash="dot", zeroline=False, showline=False),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0,
                    bgcolor="rgba(0,0,0,0)", font=dict(color=TEMA["texto_fraco"])),
    )


CONFIG_PLOTLY = {
    "displayModeBar": False,
    "scrollZoom": False,
    "locale": "pt-br",
}


# ----------------------------------------------------------- formato

def brl(valor: float, sinal: bool = False) -> str:
    """12345.6 -> 'R$ 12.345,60'."""
    if valor is None:
        valor = 0.0
    prefixo = ""
    if sinal and valor > 0:
        prefixo = "+"
    texto = f"{abs(valor):,.2f}".replace(",", "@").replace(".", ",").replace("@", ".")
    negativo = "-" if valor < 0 else ""
    return f"{negativo}{prefixo}R$ {texto}"


def pct(valor: float) -> str:
    return f"{valor:,.1f}%".replace(".", ",")


# ------------------------------------------- importação de extrato (PDF)
# Categoria usada quando nenhuma palavra-chave casa com a descrição da fatura.
CATEGORIA_NAO_ATRIBUIDA = "Não atribuído"

# Faturas de cartão costumam vir protegidas por senha. Ela NÃO fica escrita
# aqui: o app lê de .streamlit/secrets.toml (chave senha_extrato) ou da
# variável de ambiente SENHA_EXTRATO, e o campo na tela aceita outra na hora.
SENHA_EXTRATO_ENV = "SENHA_EXTRATO"


def senha_extrato_padrao() -> str:
    """Senha pré-preenchida no campo da aba de importação ('' se não houver)."""
    do_ambiente = os.environ.get(SENHA_EXTRATO_ENV, "")
    if do_ambiente:
        return do_ambiente
    try:
        import streamlit as st

        return str(st.secrets.get("senha_extrato", ""))
    except Exception:  # sem secrets.toml configurado
        return ""

# Regras de classificação automática: categoria -> palavras-chave.
# A comparação ignora acentos e maiúsculas, e casa por trecho ("uber" acha
# "UBER *TRIP SAO PAULO"). Edite à vontade — palavras mais específicas
# ganham de palavras mais curtas quando as duas casam.
PALAVRAS_CHAVE_CATEGORIA: dict[str, list[str]] = {
    "Moradia": [
        "aluguel", "imobiliaria", "condominio", "iptu", "enel", "neoenergia",
        "cemig", "copel", "cpfl", "light servicos", "energia", "sabesp",
        "caesb", "cedae", "sanepar", "comgas", "vivo", "claro", "tim ",
        "oi fibra", "net servicos", "internet", "telefonica",
    ],
    "Mercado": [
        "supermercado", "super mercado", "mercado ", "hipermercado", "atacad",
        "carrefour", "pao de acucar", "extra ", "assai", "sendas", "sams club",
        "big bompreco", "zona sul", "hortifruti", "sacolao", "quitanda",
        "mundial", "prezunic", "st marche", "oba horti",
    ],
    "Alimentação": [
        "ifood", "rappi", "uber eats", "restaurante", "lanchonete", "padaria",
        "pizzaria", "pizza", "burger", "mc donalds", "mcdonald", "bobs",
        "subway", "habibs", "china in box", "outback", "spoleto", "giraffas",
        "cafeteria", "starbucks", "doceria", "sorveteria", "acai", "bar do",
        "boteco", "churrascaria", "temakeria", "sushi",
    ],
    "Transporte": [
        "uber", "99app", "99 tecnologia", "cabify", "posto ", "ipiranga",
        "shell", "petrobras", "br mania", "combustivel", "estacionamento",
        "estapar", "pedagio", "sem parar", "conectcar", "veloe", "metro ",
        "bilhete unico", "riocard", "localiza", "movida", "unidas", "buser",
        "clickbus", "latam", "gol linhas", "azul linhas",
    ],
    "Saúde": [
        "farmacia", "drogaria", "drogasil", "droga raia", "raia drogasil",
        "pacheco", "pague menos", "panvel", "laboratorio", "clinica",
        "hospital", "odonto", "dentista", "unimed", "amil", "sulamerica",
        "hapvida", "academia", "smart fit", "smartfit", "gympass", "wellhub",
    ],
    "Educação": [
        "faculdade", "universidade", "ceub", "mensalidade", "escola",
        "colegio", "curso", "udemy", "alura", "coursera", "hotmart",
        "livraria", "cultura livr", "descomplica",
    ],
    "Lazer": [
        "cinema", "cinemark", "kinoplex", "uci ", "ingresso.com", "ticketmaster",
        "sympla", "eventim", "steam", "playstation", "xbox", "nintendo",
        "epic games", "riot games", "teatro", "museu", "parque",
    ],
    "Assinaturas": [
        "netflix", "spotify", "prime video", "amazon prime", "disney",
        "hbo max", "max.com", "globoplay", "deezer", "youtube", "google one",
        "google storage", "icloud", "apple.com", "apple servi", "microsoft",
        "office 365", "adobe", "github", "openai", "chatgpt", "anthropic",
        "claude.ai", "dropbox", "canva", "notion", "paramount", "crunchyroll",
        "telecine", "dazn", "kindle unlimited",
    ],
    "Compras": [
        "amazon", "mercadolivre", "mercado livre", "mercadolibre", "shopee",
        "aliexpress", "shein", "magazine luiza", "magalu", "americanas",
        "casas bahia", "ponto frio", "renner", "riachuelo", "c&a", "zara",
        "centauro", "netshoes", "nike", "adidas", "decathlon", "leroy merlin",
        "kalunga", "kabum", "pichau", "terabyte", "fast shop",
    ],
    "Investimentos": [
        "tesouro direto", "xp investimentos", "clear corretora", "rico invest",
        "nuinvest", "btg pactual", "avenue", "binance", "mercado bitcoin",
        "aporte",
    ],
}

# Palavras que, sozinhas na linha, denunciam cabeçalho/rodapé/total.
# A comparação é por palavra inteira, então "total" descarta "TOTAL DA FATURA"
# mas não atrapalha uma compra em "TOTALENERGIES POSTO".
PALAVRAS_IGNORADAS_EXTRATO: list[str] = [
    "total", "subtotal", "totais", "pagina", "paginas", "limite", "saldo",
    "vencimento", "demonstrativo", "fatura", "encargos", "parcelamento",
    "cotacao", "protocolo", "ouvidoria", "sac",
]

# Linhas do PDF que não são lançamentos (totais, encargos, cabeçalhos…).
# Basta o trecho aparecer na linha para ela ser descartada.
LINHAS_IGNORADAS_EXTRATO: list[str] = [
    "saldo anterior", "saldo atual", "fatura anterior", "pagamento efetuado",
    "pagamento recebido", "pagto efetuado", "total da fatura", "valor total",
    "total a pagar", "pagamento minimo", "limite total", "limite disponivel",
    "limite de credito", "vencimento", "demonstrativo", "resumo da fatura",
    "subtotal", "total nacional", "total internacional", "lancamentos nacionais",
    "lancamentos internacionais", "proximas faturas", "parcelamento da fatura",
    "cotacao do dolar", "taxa de conversao", "dolar de conversao",
    "pontos acumulados", "programa de pontos", "central de atendimento",
    "sac ", "ouvidoria", "data movimentacao", "descricao valor",
]
