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
                line=dict(color=TEMA["superficie"], width=3),
            ),
            textinfo="none",
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
    fig.update_layout(showlegend=False)
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
