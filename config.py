"""
Configuração central do dashboard: paleta, tipografia, categorias e
template dos gráficos.

A interface é neutra: dois tons de fundo, dois de texto e um acento
verde para o que é positivo. A cor forte fica reservada para os dados.

As cores das categorias são uma paleta categórica escolhida por busca e
conferida com o validador da skill de dataviz (OKLab, fundo #0F1216):
as seis primeiras — as que costumam dominar um mês — passam o piso de
visão normal (pior par ΔE 15,8) e ficam na faixa de daltonismo que exige
rótulo junto (ΔE 6,0); com as onze juntas cai para ~11 / ~5, que é o teto
matemático desse número de cores simultâneas. Por isso todo
gráfico com muitas fatias carrega rótulo ou legenda: a cor identifica,
mas nunca sozinha.
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

# Duas famílias: a sans no corpo e a serifada de display nos números —
# a mesma dupla do style.css, para o gráfico combinar com a página.
FONTE_UI = "Inter"
FONTE_NUMERO = "Instrument Serif"

# --------------------------------------------------------- categorias
# (nome, tipo, cor, ícone)
CATEGORIAS_PADRAO = [
    # Ordem importa: as primeiras são as que mais aparecem num mês, e ficam
    # com os tons mais separados entre si (ver comentário da paleta acima).
    ("Moradia", "despesa", "#3987E5", "🏠"),
    ("Alimentação", "despesa", "#C52012", "🍽️"),
    ("Mercado", "despesa", "#00AD54", "🛒"),
    ("Transporte", "despesa", "#A033AB", "🚌"),
    ("Saúde", "despesa", "#C46B91", "💊"),
    ("Carro", "despesa", "#9C7B00", "🚗"),
    ("Lazer", "despesa", "#008169", "🎬"),
    ("Educação", "despesa", "#00A7B2", "📚"),
    ("Assinaturas", "despesa", "#6450D8", "📺"),
    ("Compras", "despesa", "#BA5DDC", "👕"),
    ("Investimentos", "despesa", "#EC5022", "📈"),
    ("Outros", "despesa", "#6B7480", "📦"),
    ("Não atribuído", "despesa", "#454C57", "❓"),
    # Receitas nunca dividem gráfico com despesas, então podem ficar numa
    # família própria — verde é o sinal de dinheiro entrando.
    ("Salário", "receita", "#2FB673", "💼"),
    ("Freelance", "receita", "#8CB92B", "💻"),
    ("Rendimentos", "receita", "#0FA3A3", "🏦"),
    ("Outras entradas", "receita", "#5FD08A", "✨"),
]

# Cores da paleta antiga (colorida). A migração em database.py só repinta
# categorias que ainda estão com um destes valores — cor escolhida a mão
# pelo usuário no seletor de cor é preservada.
CORES_ANTIGAS_PADRAO = {
    # rampa cinza monocromática (paleta anterior)
    "Moradia": "#E4E8EC", "Mercado": "#D6DBE1", "Alimentação": "#C8CED6",
    "Transporte": "#BAC1CA", "Saúde": "#ACB4BF", "Educação": "#9EA7B3",
    "Lazer": "#909AA8", "Assinaturas": "#828D9C", "Compras": "#748090",
    "Investimentos": "#667385", "Outros": "#586679", "Não atribuído": "#49525F",
    "Salário": "#4CC38A", "Freelance": "#6FCFA0", "Rendimentos": "#92DBB7",
    "Outras entradas": "#B5E7CD",
    # e a paleta colorida original, para bases bem antigas
    "Moradia_v1": "#7C6BD6", "Mercado_v1": "#5FA85A", "Alimentação_v1": "#E08A3C",
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
    # Transporte = deslocamento que você não dirige (app, ônibus, metrô, viagem)
    "Transporte": [
        "uber", "99app", "99 tecnologia", "cabify", "indriver", "metro ",
        "metro rio", "bilhete unico", "riocard", "bom onibus", "vlt", "brt ",
        "trem ", "supervia", "buser", "clickbus", "rodoviaria", "latam",
        "gol linhas", "azul linhas", "localiza", "movida", "unidas",
    ],
    # Carro = o custo de ter o seu (combustível, manutenção, imposto, seguro)
    "Carro": [
        "combustivel", "posto ", "posto de", "auto posto", "ipiranga", "shell",
        "petrobras", "br mania", "gasolina", "etanol", "alcool", "diesel",
        "gnv ", "estacionamento", "estapar", "parking", "pedagio", "sem parar",
        "conectcar", "veloe", "autopass", "oficina", "mecanica", "auto center",
        "autopecas", "auto pecas", "funilaria", "borracharia", "pneu",
        "alinhamento", "balanceamento", "lava jato", "lava rapido", "lavagem",
        "ipva", "licenciamento", "detran", "dpvat", "seguro auto",
        "seguro automovel", "porto seguro auto", "multa transito",
        "troca de oleo", "revisao",
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
