"""Gráficos do dashboard. Cada função devolve uma figura Plotly pronta."""

from __future__ import annotations

import calendar
from datetime import date

import pandas as pd
import plotly.graph_objects as go

from config import TEMA, FONTE_NUMERO, FONTE_UI, brl, layout_base, rotulo_curto


def _vazio(mensagem: str, altura: int = 320) -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(
        text=mensagem, showarrow=False,
        font=dict(family=f"{FONTE_UI}, sans-serif", size=13, color=TEMA["texto_fraco"]),
    )
    fig.update_layout(**layout_base(altura))
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return fig


# ------------------------------------------------ despesas por categoria

def rosca_categorias(df: pd.DataFrame, cores: dict[str, str], altura: int = 330) -> go.Figure:
    despesas = df[df["tipo"] == "despesa"]
    if despesas.empty:
        return _vazio("Sem despesas neste mês.", altura)

    serie = despesas.groupby("categoria")["valor"].sum().sort_values(ascending=False)
    total = float(serie.sum())

    fig = go.Figure(
        go.Pie(
            labels=serie.index,
            values=serie.values,
            hole=0.68,
            sort=False,
            direction="clockwise",
            marker=dict(
                colors=[cores.get(c, TEMA["texto_fraco"]) for c in serie.index],
                line=dict(color=TEMA["fundo"], width=2),
            ),
            # rótulo na própria fatia: a cor identifica, mas nunca sozinha
            texttemplate="%{label}<br>%{percent}",
            textposition="inside",
            insidetextorientation="horizontal",
            textfont=dict(family=f"{FONTE_UI}, sans-serif", size=12, color="#FFFFFF"),
            hovertemplate="<b>%{label}</b><br>%{customdata}<br>%{percent}<extra></extra>",
            customdata=[brl(v) for v in serie.values],
        )
    )
    fig.add_annotation(
        text=f"<span style='font-size:12px;color:{TEMA['texto_fraco']}'>total do mês</span>"
             f"<br><span style='font-size:22px;color:{TEMA['texto']};"
             f"font-family:{FONTE_NUMERO}'>{brl(total)}</span>",
        showarrow=False, font=dict(family=f"{FONTE_UI}, sans-serif"),
    )
    fig.update_layout(**layout_base(altura, margem=dict(l=0, r=0, t=6, b=6)))
    # esconde o rótulo que não couber, em vez de deixar texto espremido
    fig.update_layout(showlegend=False, uniformtext=dict(minsize=10, mode="hide"))
    return fig


# --------------------------------------------------- evolução mensal

def evolucao_mensal(df: pd.DataFrame, meses: int = 8, altura: int = 330) -> go.Figure:
    if df.empty:
        return _vazio("Cadastre lançamentos para ver a evolução.", altura)

    base = df.copy()
    base["competencia"] = base["data"].dt.strftime("%Y-%m")
    tabela = (base.pivot_table(index="competencia", columns="tipo", values="valor",
                               aggfunc="sum", fill_value=0.0)
                  .sort_index().tail(meses))
    for coluna in ("receita", "despesa"):
        if coluna not in tabela:
            tabela[coluna] = 0.0
    tabela["saldo"] = tabela["receita"] - tabela["despesa"]
    rotulos = [rotulo_curto(c) for c in tabela.index]

    fig = go.Figure()
    fig.add_bar(x=rotulos, y=tabela["receita"], name="Entradas",
                marker_color=TEMA["entrada"], marker_line_width=0, width=0.34, offset=-0.36,
                hovertemplate="Entradas<br>%{customdata}<extra></extra>",
                customdata=[brl(v) for v in tabela["receita"]])
    fig.add_bar(x=rotulos, y=tabela["despesa"], name="Saídas",
                marker_color=TEMA["saida"], marker_line_width=0, width=0.34, offset=0.02,
                hovertemplate="Saídas<br>%{customdata}<extra></extra>",
                customdata=[brl(v) for v in tabela["despesa"]])
    fig.add_scatter(x=rotulos, y=tabela["saldo"], name="Saldo", mode="lines+markers",
                    line=dict(color=TEMA["destaque"], width=2, shape="spline"),
                    marker=dict(size=6, color=TEMA["fundo"],
                                line=dict(color=TEMA["destaque"], width=2)),
                    hovertemplate="Saldo<br>%{customdata}<extra></extra>",
                    customdata=[brl(v) for v in tabela["saldo"]])

    fig.update_layout(**layout_base(altura, margem=dict(l=8, r=8, t=30, b=8)))
    fig.update_layout(barmode="overlay", hovermode="x unified")
    fig.update_yaxes(tickprefix="R$ ", tickformat=",.0f")
    return fig


# ------------------------------------------------------ ritmo do mês

def acumulado_diario(df_mes: pd.DataFrame, df_anterior: pd.DataFrame,
                     competencia: str, altura: int = 300) -> go.Figure:
    ano, mes = map(int, competencia.split("-"))
    dias_no_mes = calendar.monthrange(ano, mes)[1]
    hoje = date.today()
    limite = hoje.day if (ano, mes) == (hoje.year, hoje.month) else dias_no_mes

    def acumular(dados: pd.DataFrame, ate: int) -> list[float]:
        despesas = dados[dados["tipo"] == "despesa"]
        if despesas.empty:
            return [0.0] * ate
        por_dia = despesas.groupby(despesas["data"].dt.day)["valor"].sum()
        return [float(por_dia.reindex(range(1, d + 1), fill_value=0).sum())
                for d in range(1, ate + 1)]

    atual = acumular(df_mes, limite)
    passado = acumular(df_anterior, dias_no_mes)

    if not any(atual) and not any(passado):
        return _vazio("Sem despesas para comparar.", altura)

    fig = go.Figure()
    if any(passado):
        fig.add_scatter(x=list(range(1, len(passado) + 1)), y=passado, name="Mês anterior",
                        mode="lines", line=dict(color=TEMA["texto_fraco"], width=1.5, dash="dot"),
                        hovertemplate="Dia %{x} · mês anterior<br>%{customdata}<extra></extra>",
                        customdata=[brl(v) for v in passado])
    fig.add_scatter(x=list(range(1, len(atual) + 1)), y=atual, name="Este mês",
                    mode="lines", line=dict(color=TEMA["saida"], width=2.5, shape="spline"),
                    fill="tozeroy", fillcolor="rgba(185,191,199,0.10)",
                    hovertemplate="Dia %{x}<br>%{customdata}<extra></extra>",
                    customdata=[brl(v) for v in atual])

    fig.update_layout(**layout_base(altura, margem=dict(l=8, r=8, t=30, b=8)))
    fig.update_layout(hovermode="x unified")
    fig.update_xaxes(title_text="dia do mês", range=[1, dias_no_mes], dtick=5)
    fig.update_yaxes(tickprefix="R$ ", tickformat=",.0f")
    return fig


# ------------------------------------------------------- maiores gastos

def maiores_gastos(df: pd.DataFrame, cores: dict[str, str], quantidade: int = 8,
                   altura: int = 300) -> go.Figure:
    despesas = df[df["tipo"] == "despesa"].nlargest(quantidade, "valor")
    if despesas.empty:
        return _vazio("Sem despesas neste mês.", altura)

    despesas = despesas.iloc[::-1]
    rotulos = [f"{d:%d/%m} · {t[:26]}" for d, t in zip(despesas["data"], despesas["descricao"])]

    fig = go.Figure(
        go.Bar(
            x=despesas["valor"], y=rotulos, orientation="h",
            marker=dict(color=[cores.get(c, TEMA["texto_fraco"]) for c in despesas["categoria"]]),
            marker_line_width=0, width=0.62,
            text=[brl(v) for v in despesas["valor"]],
            textposition="outside",
            textfont=dict(color=TEMA["texto_fraco"], size=12),
            hovertemplate="<b>%{y}</b><br>%{customdata[0]}<br>%{customdata[1]}<extra></extra>",
            customdata=list(zip(despesas["categoria"], [brl(v) for v in despesas["valor"]])),
        )
    )
    fig.update_layout(**layout_base(altura, margem=dict(l=8, r=70, t=8, b=8)))
    fig.update_xaxes(visible=False, range=[0, float(despesas["valor"].max()) * 1.28])
    fig.update_yaxes(showgrid=False, tickfont=dict(size=12))
    return fig


# --------------------------------------------------------- pagamentos

def por_metodo(df: pd.DataFrame, altura: int = 240) -> go.Figure:
    despesas = df[df["tipo"] == "despesa"]
    if despesas.empty:
        return _vazio("Sem despesas neste mês.", altura)

    serie = despesas.groupby("metodo")["valor"].sum().sort_values()
    fig = go.Figure(
        go.Bar(x=serie.values, y=serie.index, orientation="h",
               marker_color=TEMA["destaque"], marker_line_width=0, width=0.55,
               text=[brl(v) for v in serie.values], textposition="outside",
               textfont=dict(color=TEMA["texto_fraco"], size=12),
               hovertemplate="%{y}<br>%{text}<extra></extra>")
    )
    fig.update_layout(**layout_base(altura, margem=dict(l=8, r=70, t=8, b=8)))
    fig.update_xaxes(visible=False, range=[0, float(serie.max()) * 1.3])
    fig.update_yaxes(showgrid=False)
    return fig


# ============================================================ novos estilos
# Todos reaproveitam o mesmo mapa `cores` das categorias, para a mesma
# categoria ter a mesma cor em qualquer gráfico da tela.

def _despesas_por_mes(df: pd.DataFrame, meses: int) -> pd.DataFrame:
    """Tabela categoria × competência com a soma de despesas."""
    despesas = df[df["tipo"] == "despesa"]
    if despesas.empty:
        return pd.DataFrame()
    base = despesas.copy()
    base["competencia"] = base["data"].dt.strftime("%Y-%m")
    tabela = base.pivot_table(index="categoria", columns="competencia",
                              values="valor", aggfunc="sum", fill_value=0.0)
    return tabela[sorted(tabela.columns)[-meses:]]


def _rgba(cor_hex: str, alfa: float) -> str:
    cor_hex = cor_hex.lstrip("#")
    r, g, b = (int(cor_hex[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{alfa})"


def comparativo_categorias(df: pd.DataFrame, cores: dict[str, str],
                           meses: int = 3, quantidade: int = 8,
                           altura: int = 420) -> go.Figure:
    """Barras horizontais: quanto cada categoria custou em cada um dos últimos meses.

    A cor continua sendo a da categoria; o mês entra como opacidade (mais
    claro = mais antigo), para não gastar uma segunda escala de cor.
    """
    tabela = _despesas_por_mes(df, meses)
    if tabela.empty:
        return _vazio("Sem despesas para comparar.", altura)

    tabela = tabela.loc[tabela.sum(axis=1).sort_values().index][-quantidade:]
    competencias = list(tabela.columns)
    opacidades = [0.4 + 0.6 * (i + 1) / len(competencias) for i in range(len(competencias))]

    fig = go.Figure()
    for i, competencia in enumerate(competencias):
        fig.add_bar(
            y=list(tabela.index), x=tabela[competencia], orientation="h",
            name=rotulo_curto(competencia),
            showlegend=False,   # a legenda vem das amostras neutras abaixo
            marker=dict(
                color=[_rgba(cores.get(c, TEMA["texto_fraco"]), opacidades[i])
                       for c in tabela.index],
                line=dict(color=TEMA["fundo"], width=2),   # respiro entre barras
            ),
            hovertemplate="<b>%{y}</b><br>" + rotulo_curto(competencia)
                          + "<br>%{customdata}<extra></extra>",
            customdata=[brl(v) for v in tabela[competencia]],
        )

    # A barra usa a cor da categoria, então o quadradinho da legenda não pode
    # ser colorido (seria a cor de uma categoria qualquer). Estas séries vazias
    # existem só para a legenda mostrar o que cada nível de opacidade significa.
    # São marcadores, e não barras: uma barra vazia entraria no agrupamento e
    # espremeria as de verdade.
    for i, competencia in enumerate(competencias):
        fig.add_scatter(
            y=[None], x=[None], mode="markers", name=rotulo_curto(competencia),
            marker=dict(symbol="square", size=11,
                        color=_rgba(TEMA["texto"], opacidades[i])),
            hoverinfo="skip",
        )

    fig.update_layout(**layout_base(altura, margem=dict(l=8, r=16, t=34, b=8)))
    fig.update_layout(barmode="group", bargap=0.35, bargroupgap=0.08)
    fig.update_xaxes(tickprefix="R$ ", tickformat=",.0f", showgrid=True,
                     gridcolor=TEMA["linha"], griddash="dot")
    fig.update_yaxes(showgrid=False, tickfont=dict(size=12))
    return fig


def treemap_categorias(df: pd.DataFrame, cores: dict[str, str],
                       altura: int = 420) -> go.Figure:
    """Treemap do mês: a área é o peso da categoria no total."""
    despesas = df[df["tipo"] == "despesa"]
    if despesas.empty:
        return _vazio("Sem despesas neste mês.", altura)

    serie = despesas.groupby("categoria")["valor"].sum().sort_values(ascending=False)
    total = float(serie.sum())

    fig = go.Figure(go.Treemap(
        labels=list(serie.index),
        parents=[""] * len(serie),
        values=list(serie.values),
        marker=dict(
            colors=[cores.get(c, TEMA["texto_fraco"]) for c in serie.index],
            line=dict(color=TEMA["fundo"], width=2),
        ),
        # o rótulo dentro do bloco é o que garante a leitura sem depender da cor
        texttemplate="<b>%{label}</b><br>%{customdata}<br>%{percentRoot}",
        textfont=dict(family=f"{FONTE_UI}, sans-serif", size=13, color="#FFFFFF"),
        customdata=[brl(v) for v in serie.values],
        hovertemplate="<b>%{label}</b><br>%{customdata}<br>%{percentRoot} do mês<extra></extra>",
        tiling=dict(pad=2),
        sort=True,
    ))
    fig.update_layout(**layout_base(altura, margem=dict(l=0, r=0, t=0, b=0)))
    fig.update_layout(
        uniformtext=dict(minsize=11, mode="hide"),
        annotations=[dict(
            text=f"total {brl(total)}", x=1, y=-0.04, xref="paper", yref="paper",
            xanchor="right", showarrow=False,
            font=dict(size=12, color=TEMA["texto_fraco"]),
        )],
    )
    return fig


def composicao_mensal(df: pd.DataFrame, cores: dict[str, str], meses: int = 8,
                      principais: int = 6, altura: int = 380) -> go.Figure:
    """Área empilhada: como a composição do gasto mudou ao longo dos meses.

    Só as `principais` categorias ficam separadas; o resto vira "Outras",
    porque acima disso a leitura por cor deixa de funcionar.
    """
    tabela = _despesas_por_mes(df, meses)
    if tabela.empty or len(tabela.columns) < 2:
        return _vazio("São necessários pelo menos dois meses de despesas.", altura)

    ordem = tabela.sum(axis=1).sort_values(ascending=False)
    destaque = list(ordem.index[:principais])
    resto = [c for c in ordem.index if c not in destaque]
    empilhado = tabela.loc[destaque]
    if resto:
        empilhado.loc["Outras"] = tabela.loc[resto].sum()

    rotulos = [rotulo_curto(c) for c in empilhado.columns]
    fig = go.Figure()
    for categoria in empilhado.index:
        cor = cores.get(categoria, TEMA["texto_fraco"])
        fig.add_scatter(
            x=rotulos, y=empilhado.loc[categoria], name=str(categoria),
            mode="lines", stackgroup="gasto",
            line=dict(width=2, color=TEMA["fundo"]),   # fio de respiro entre faixas
            fillcolor=_rgba(cor, 0.85),
            hovertemplate=f"<b>{categoria}</b><br>%{{customdata}}<extra></extra>",
            customdata=[brl(v) for v in empilhado.loc[categoria]],
        )

    fig.update_layout(**layout_base(altura, margem=dict(l=8, r=8, t=34, b=8)))
    fig.update_layout(hovermode="x unified")
    fig.update_yaxes(tickprefix="R$ ", tickformat=",.0f")
    return fig
