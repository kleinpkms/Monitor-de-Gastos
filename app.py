"""
Dashboard financeiro pessoal — controle de gastos mensais.

Como rodar:
    pip install -r requirements.txt
    streamlit run app.py
"""

from __future__ import annotations

import calendar
import os
from datetime import date

import pandas as pd
import streamlit as st

import charts
import database as db
import extrato
from config import (CATEGORIA_NAO_ATRIBUIDA, CONFIG_PLOTLY, METODOS, TEMA,
                    TIPOS, brl, nome_competencia, pct, senha_extrato_padrao)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

st.set_page_config(
    page_title="Dashboard financeiro",
    page_icon="◍",
    layout="wide",
    initial_sidebar_state="expanded",
)


def carregar_css() -> None:
    with open(os.path.join(BASE_DIR, "style.css"), encoding="utf-8") as arquivo:
        st.markdown(f"<style>{arquivo.read()}</style>", unsafe_allow_html=True)


def mes_anterior(competencia: str) -> str:
    ano, mes = map(int, competencia.split("-"))
    return f"{ano - 1}-12" if mes == 1 else f"{ano}-{mes - 1:02d}"


def cartao(rotulo: str, valor: str, classe: str = "", apoio: str = "") -> str:
    extra = f"<div class='apoio'>{apoio}</div>" if apoio else ""
    return (f"<div class='cartao'><div class='rotulo'>{rotulo}</div>"
            f"<div class='numero numero-medio {classe}'>{valor}</div>{extra}</div>")


carregar_css()
db.criar_schema()

cores = db.mapa_cores()
icones = db.mapa_icones()
categorias = db.listar_categorias()

# ============================================================ barra lateral

with st.sidebar:
    st.markdown("<div class='secao'>◍ Minhas finanças</div>", unsafe_allow_html=True)

    competencias = db.competencias_disponiveis()
    competencia = st.selectbox(
        "Mês de referência", competencias,
        format_func=nome_competencia, key="competencia",
    )

    st.divider()
    st.markdown("<div class='secao'>Novo lançamento</div>", unsafe_allow_html=True)

    tipo_novo = st.segmented_control(
        "Tipo", TIPOS, default="despesa", format_func=str.capitalize,
        key="tipo_novo",
    ) or "despesa"

    with st.form("novo_lancamento", clear_on_submit=True, border=False):
        descricao = st.text_input("Descrição", placeholder="Almoço, aluguel, salário…")
        col_a, col_b = st.columns(2)
        valor = col_a.number_input("Valor (R$)", min_value=0.0, step=10.0, format="%.2f")
        data_lanc = col_b.date_input("Data", value=date.today(), format="DD/MM/YYYY")

        opcoes_categoria = categorias[categorias["tipo"] == tipo_novo]["nome"].tolist()
        categoria = st.selectbox(
            "Categoria", opcoes_categoria or ["Outros"],
            format_func=lambda c: f"{icones.get(c, '📦')}  {c}",
        )
        metodo = st.selectbox("Forma de pagamento", METODOS)
        fixo = st.checkbox("Repete todo mês", help="Permite copiar este lançamento para os próximos meses.")

        if st.form_submit_button("Adicionar lançamento", type="primary"):
            if not descricao.strip():
                st.warning("Escreva uma descrição para identificar o lançamento.")
            elif valor <= 0:
                st.warning("Informe um valor maior que zero.")
            else:
                db.inserir_lancamento(data_lanc, descricao, categoria, tipo_novo,
                                      valor, metodo, fixo)
                st.success(f"{descricao} · {brl(valor)} registrado.")
                st.rerun()

    st.divider()
    anterior = mes_anterior(competencia)
    if st.button(f"Repetir fixos de {nome_competencia(anterior).split(' de ')[0]}"):
        criados = db.repetir_fixos(anterior, competencia)
        if criados:
            st.success(f"{criados} lançamento(s) copiado(s).")
            st.rerun()
        else:
            st.info("Nada novo para copiar — os fixos já estão neste mês.")

# ================================================================ dados

df_mes = db.listar_lancamentos(competencia=competencia)
df_ant = db.listar_lancamentos(competencia=mes_anterior(competencia))
df_todos = db.listar_lancamentos()

receitas = float(df_mes.loc[df_mes["tipo"] == "receita", "valor"].sum())
despesas = float(df_mes.loc[df_mes["tipo"] == "despesa", "valor"].sum())
saldo = receitas - despesas
despesas_ant = float(df_ant.loc[df_ant["tipo"] == "despesa", "valor"].sum())
variacao = ((despesas - despesas_ant) / despesas_ant * 100) if despesas_ant else 0.0
taxa_poupanca = (saldo / receitas * 100) if receitas else 0.0

ano_ref, mes_ref = map(int, competencia.split("-"))
dias_no_mes = calendar.monthrange(ano_ref, mes_ref)[1]
hoje = date.today()
mes_corrente = (ano_ref, mes_ref) == (hoje.year, hoje.month)
dias_corridos = hoje.day if mes_corrente else dias_no_mes
media_diaria = despesas / max(dias_corridos, 1)
projecao = media_diaria * dias_no_mes

# ============================================================== cabeçalho

st.markdown(
    f"<div class='topo'><h1>Gastos de {nome_competencia(competencia)}</h1>"
    f"<span>{len(df_mes)} lançamentos</span></div>",
    unsafe_allow_html=True,
)
st.markdown(
    "<div class='apoio' style='margin-bottom:26px'>"
    "Tudo é salvo em <code>financas.db</code>, no mesmo diretório do projeto.</div>",
    unsafe_allow_html=True,
)

col1, col2, col3, col4 = st.columns([1.7, 1, 1, 1], gap="small")

classe_saldo = "entrada" if saldo >= 0 else "saida"
rotulo_saldo = "Sobrou no mês" if saldo >= 0 else "Faltou no mês"
col1.markdown(
    f"""<div class='cartao-saldo'>
        <div class='rotulo'>{rotulo_saldo}</div>
        <div class='numero numero-grande {classe_saldo}'>{brl(saldo)}</div>
        <div class='apoio'>{brl(receitas)} entraram · {brl(despesas)} saíram<br>
        Taxa de poupança de {pct(taxa_poupanca)} do que você recebeu.</div>
    </div>""",
    unsafe_allow_html=True,
)

col2.markdown(
    cartao("Entradas", brl(receitas), "entrada",
           f"{int((df_mes['tipo'] == 'receita').sum())} registro(s)"),
    unsafe_allow_html=True,
)

if despesas_ant:
    seta = "▲" if variacao > 0 else "▼"
    comparativo = f"{seta} {pct(abs(variacao))} vs. o mês anterior"
else:
    comparativo = "Sem mês anterior para comparar"
col3.markdown(cartao("Saídas", brl(despesas), "saida", comparativo), unsafe_allow_html=True)

if mes_corrente:
    apoio_ritmo = f"Projeção do mês fechado: {brl(projecao)}"
else:
    apoio_ritmo = f"Ao longo de {dias_no_mes} dias"
col4.markdown(
    cartao("Média por dia", brl(media_diaria), "", apoio_ritmo),
    unsafe_allow_html=True,
)

st.markdown("<div style='height:34px'></div>", unsafe_allow_html=True)

aba_visao, aba_lanc, aba_extrato, aba_orc, aba_ajustes = st.tabs(
    ["Visão geral", "Lançamentos", "Importar extrato", "Orçamento", "Ajustes"]
)

# ============================================================ visão geral

with aba_visao:
    esq, dir_ = st.columns([1, 1.35], gap="medium")

    with esq:
        st.markdown("<div class='secao'>Para onde o dinheiro foi</div>", unsafe_allow_html=True)
        st.plotly_chart(charts.rosca_categorias(df_mes, cores),
                        config=CONFIG_PLOTLY, width="stretch")
        if not df_mes[df_mes["tipo"] == "despesa"].empty:
            resumo = (df_mes[df_mes["tipo"] == "despesa"]
                      .groupby("categoria")["valor"].sum().sort_values(ascending=False))
            linhas = []
            for nome, total in resumo.head(6).items():
                fatia = total / despesas * 100 if despesas else 0
                linhas.append(
                    f"<div class='linha-resumo'>"
                    f"<span><span style='color:{cores.get(nome, TEMA['texto_fraco'])}'>●</span>"
                    f"&nbsp; {icones.get(nome, '')} {nome}</span>"
                    f"<span class='numero' style='font-size:0.86rem'>{brl(total)} "
                    f"<span class='neutro' style='font-size:0.76rem'>{pct(fatia)}</span></span></div>"
                )
            st.markdown("".join(linhas), unsafe_allow_html=True)

    with dir_:
        st.markdown(
            "<div class='secao'>Entradas, saídas e saldo <small>· últimos meses</small></div>",
            unsafe_allow_html=True,
        )
        st.plotly_chart(charts.evolucao_mensal(df_todos),
                        config=CONFIG_PLOTLY, width="stretch")

        st.markdown(
            "<div class='secao'>Ritmo de gasto <small>· acumulado no mês</small></div>",
            unsafe_allow_html=True,
        )
        st.plotly_chart(charts.acumulado_diario(df_mes, df_ant, competencia),
                        config=CONFIG_PLOTLY, width="stretch")

    st.divider()
    baixo_esq, baixo_dir = st.columns([1.4, 1], gap="medium")
    with baixo_esq:
        st.markdown("<div class='secao'>Maiores gastos do mês</div>", unsafe_allow_html=True)
        st.plotly_chart(charts.maiores_gastos(df_mes, cores),
                        config=CONFIG_PLOTLY, width="stretch")
    with baixo_dir:
        st.markdown("<div class='secao'>Como você pagou</div>", unsafe_allow_html=True)
        st.plotly_chart(charts.por_metodo(df_mes), config=CONFIG_PLOTLY, width="stretch")

# ============================================================ lançamentos

with aba_lanc:
    filtro1, filtro2, filtro3 = st.columns([1, 2, 2])
    tipo_filtro = filtro1.multiselect("Tipo", TIPOS, format_func=str.capitalize)
    cat_filtro = filtro2.multiselect("Categorias", categorias["nome"].tolist())
    busca = filtro3.text_input("Buscar", placeholder="Parte da descrição ou observação")

    visivel = db.listar_lancamentos(competencia, tipo_filtro or None,
                                    cat_filtro or None, busca)

    st.markdown(
        "<div class='apoio'>Marque <strong>Excluir</strong> para apagar a linha na hora — "
        "o gráfico já reflete. As outras edições entram ao clicar em salvar; a última "
        "linha vazia serve para incluir um lançamento.</div>",
        unsafe_allow_html=True,
    )

    # a coluna "excluir" existe só na tela: apaga na mesma interação
    tabela_lanc = visivel.copy()
    tabela_lanc.insert(0, "excluir", False)

    editado = st.data_editor(
        tabela_lanc,
        key=f"editor_{competencia}_{len(visivel)}",
        num_rows="dynamic",
        width="stretch",
        height=460,
        hide_index=True,
        column_config={
            "id": None,
            "excluir": st.column_config.CheckboxColumn(
                "Excluir", width="small",
                help="Apaga este lançamento imediatamente, sem passar por salvar."),
            "data": st.column_config.DateColumn("Data", format="DD/MM/YYYY", width="small"),
            "descricao": st.column_config.TextColumn("Descrição", width="medium"),
            "categoria": st.column_config.SelectboxColumn(
                "Categoria", options=categorias["nome"].tolist(), width="small"),
            "tipo": st.column_config.SelectboxColumn("Tipo", options=TIPOS, width="small"),
            "valor": st.column_config.NumberColumn(
                "Valor", format="R$ %.2f", min_value=0.0, width="small"),
            "metodo": st.column_config.SelectboxColumn(
                "Pagamento", options=METODOS, width="small"),
            "fixo": st.column_config.CheckboxColumn("Fixo", width="small"),
            "obs": st.column_config.TextColumn("Observação", width="medium"),
        },
    )

    marcados_excluir = [
        int(id_) for id_, marcado in zip(editado["id"], editado["excluir"])
        if bool(marcado) and pd.notna(id_)
    ]
    if marcados_excluir:
        apagados = visivel[visivel["id"].isin(marcados_excluir)]
        db.excluir_lancamentos(marcados_excluir)
        if len(apagados) == 1:
            linha_apagada = apagados.iloc[0]
            aviso = f"{linha_apagada['descricao']} · {brl(linha_apagada['valor'])} excluído."
        else:
            aviso = f"{len(marcados_excluir)} lançamentos excluídos."
        st.toast(aviso, icon="🗑️")
        st.rerun()

    acao1, acao2, _ = st.columns([1, 1, 3])

    if acao1.button("Salvar alterações", type="primary"):
        originais = visivel.set_index("id")
        ids_editados = {int(i) for i in editado["id"].dropna()}
        removidos = [int(i) for i in originais.index if int(i) not in ids_editados]
        db.excluir_lancamentos(removidos)

        alterados = novos = 0
        for _, linha in editado.iterrows():
            data_ = pd.to_datetime(linha["data"], errors="coerce")
            if pd.isna(data_) or not str(linha["descricao"] or "").strip():
                continue
            valores = (data_.strftime("%Y-%m-%d"), str(linha["descricao"]).strip(),
                       linha["categoria"] or "Outros", linha["tipo"] or "despesa",
                       float(linha["valor"] or 0), linha["metodo"] or "Pix",
                       bool(linha["fixo"]), str(linha["obs"] or ""))
            if pd.isna(linha["id"]):
                db.inserir_lancamento(*valores)
                novos += 1
            else:
                antes = originais.loc[int(linha["id"])]
                atual = (antes["data"].strftime("%Y-%m-%d"), antes["descricao"],
                         antes["categoria"], antes["tipo"], float(antes["valor"]),
                         antes["metodo"], bool(antes["fixo"]), str(antes["obs"] or ""))
                if atual != valores:
                    db.atualizar_lancamento(int(linha["id"]), *valores)
                    alterados += 1

        partes = []
        if novos:
            partes.append(f"{novos} incluído(s)")
        if alterados:
            partes.append(f"{alterados} atualizado(s)")
        if removidos:
            partes.append(f"{len(removidos)} removido(s)")
        st.toast(" · ".join(partes) if partes else "Nada mudou.", icon="✅")
        st.rerun()

    acao2.download_button("Baixar CSV", db.exportar_csv(),
                          file_name=f"lancamentos_{competencia}.csv", mime="text/csv")

# ========================================================= importar extrato

with aba_extrato:
    st.markdown(
        "<div class='secao'>Fatura do cartão em PDF</div>"
        "<div class='apoio'>Envie a fatura, confira o que foi lido — a categoria vem "
        "sugerida pelas palavras-chave de <code>config.py</code> — e só então confirme. "
        "Lançamentos com a mesma data, descrição e valor já na base vêm desmarcados.</div>",
        unsafe_allow_html=True,
    )
    st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

    col_pdf, col_opcoes = st.columns([2, 1], gap="large")

    with col_pdf:
        pdf_fatura = st.file_uploader(
            "Arquivo da fatura", type=["pdf"], key="pdf_extrato",
            help="Lê linhas no padrão data + descrição + valor (DD/MM, DD/MM/AAAA ou 05 MAR).",
        )
        senha_extrato = st.text_input(
            "Senha do PDF", type="password", value=senha_extrato_padrao(),
            key="senha_extrato",
            help="A fatura do banco vem protegida. Deixe em branco se o arquivo abrir sem senha.",
        )
    with col_opcoes:
        ano_extrato = st.number_input(
            "Ano da fatura", min_value=2000, max_value=2100, step=1,
            value=int(competencia.split("-")[0]),
            help="Usado quando a fatura traz só dia e mês.",
        )
        metodo_extrato = st.selectbox(
            "Forma de pagamento", METODOS, index=METODOS.index("Crédito"),
            key="metodo_extrato",
        )

    if pdf_fatura is not None and st.button("Ler fatura", type="primary"):
        for chave in ("extrato_lido", "extrato_paginas", "extrato_diagnostico",
                      "extrato_pulados", "extrato_cortou",
                          "extrato_candidatas"):
            st.session_state.pop(chave, None)
        try:
            with st.spinner("Lendo o PDF…"):
                leitura = extrato.ler_fatura(pdf_fatura, int(ano_extrato), senha_extrato)
            st.session_state["extrato_lido"] = leitura.transacoes
            st.session_state["extrato_arquivo"] = pdf_fatura.name
            st.session_state["extrato_paginas"] = leitura.paginas
            st.session_state["extrato_diagnostico"] = leitura.diagnostico
            st.session_state["extrato_metodo"] = leitura.metodo
            st.session_state["extrato_pulados"] = leitura.pagamentos_ignorados
            st.session_state["extrato_cortou"] = leitura.cortou_futuro
            st.session_state["extrato_candidatas"] = leitura.candidatas
        except Exception as erro:
            st.error(f"Não deu para ler o PDF: {erro}")

    lidas = st.session_state.get("extrato_lido")
    paginas_pdf = st.session_state.get("extrato_paginas")

    pulados_pagto = st.session_state.get("extrato_pulados", 0)
    if pulados_pagto:
        st.info(
            f"{pulados_pagto} linha(s) de pagamento/estorno (valor com \"+\" na fatura) "
            "ficaram de fora — elas abatem a fatura, não são despesa."
        )
    if st.session_state.get("extrato_cortou"):
        st.caption(
            "A seção \"Próxima fatura\" foi descartada: compras futuras e parcelas "
            "a vencer entram quando a fatura delas chegar."
        )

    if lidas is not None and lidas.empty:
        st.warning(
            "Nenhuma transação foi reconhecida neste PDF. Abra o texto extraído abaixo "
            "para ver como a fatura está escrita — com esse trecho dá para ajustar o "
            "padrão de leitura em `extrato.py`."
        )

    # ------------------------------------------------ depuração da leitura
    if paginas_pdf is not None:
        nada_lido = lidas is not None and lidas.empty
        with st.expander("Texto extraído do PDF (conferência)", expanded=nada_lido):
            for nota in st.session_state.get("extrato_diagnostico", []):
                st.markdown(f"<div class='apoio'>· {nota}</div>", unsafe_allow_html=True)
            st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

            # linhas que parecem lançamento e não casaram: o repr() mostra
            # o caractere invisível (traço diferente, espaço estranho…)
            candidatas = st.session_state.get("extrato_candidatas") or []
            if candidatas:
                st.markdown(
                    "<div class='secao'>Linhas suspeitas, caractere por caractere"
                    "<small> · é isto que revela espaço ou traço invisível</small></div>",
                    unsafe_allow_html=True,
                )
                for linha_candidata in candidatas:
                    st.code(linha_candidata)

            texto_bruto = "\n".join(paginas_pdf)
            st.download_button(
                "Baixar o texto extraído", texto_bruto.encode("utf-8"),
                file_name="fatura_texto.txt", mime="text/plain",
            )
            for numero, texto_pagina in enumerate(paginas_pdf, 1):
                st.markdown(
                    f"<div class='apoio' style='margin-top:10px'>Página {numero} — "
                    f"{len(texto_pagina)} caractere(s)</div>",
                    unsafe_allow_html=True,
                )
                st.code(texto_pagina or "(sem texto nesta página)", language=None)

    if lidas is not None and not lidas.empty:
        st.divider()
        novos = int(lidas["importar"].sum())
        duplicados = len(lidas) - novos
        resumo = f"{len(lidas)} transação(ões) lidas de {st.session_state.get('extrato_arquivo', 'fatura')}"
        if duplicados:
            resumo += f" · {duplicados} já estão na base"
        sem_categoria = int((lidas["categoria"] == CATEGORIA_NAO_ATRIBUIDA).sum())
        if sem_categoria:
            resumo += f" · {sem_categoria} sem categoria sugerida"
        metodo_leitura = st.session_state.get("extrato_metodo", "")
        if metodo_leitura:
            resumo += f" · lidas por {metodo_leitura}"
        st.markdown(f"<div class='secao'>Revisar antes de importar <small>· {resumo}</small></div>",
                    unsafe_allow_html=True)

        revisado = st.data_editor(
            lidas,
            key="editor_extrato",
            width="stretch",
            height=440,
            hide_index=True,
            column_config={
                "importar": st.column_config.CheckboxColumn("Importar", width="small"),
                "data": st.column_config.DateColumn("Data", format="DD/MM/YYYY", width="small"),
                "descricao": st.column_config.TextColumn("Descrição", width="large"),
                "categoria": st.column_config.SelectboxColumn(
                    "Categoria", options=categorias["nome"].tolist(), width="medium"),
                "tipo": st.column_config.SelectboxColumn("Tipo", options=TIPOS, width="small"),
                "valor": st.column_config.NumberColumn(
                    "Valor", format="R$ %.2f", min_value=0.0, width="small"),
                "situacao": st.column_config.TextColumn("Situação", disabled=True, width="small"),
            },
        )

        marcados = revisado[revisado["importar"].fillna(False).astype(bool)]
        total_marcado = float(marcados.loc[marcados["tipo"] == "despesa", "valor"].sum())

        conf1, conf2 = st.columns([1, 2])
        with conf1:
            confirmar = st.button(
                f"Confirmar importação ({len(marcados)})", type="primary",
                disabled=marcados.empty,
            )
            if st.button("Descartar leitura"):
                for chave in ("extrato_lido", "extrato_arquivo", "extrato_paginas",
                              "extrato_diagnostico", "extrato_metodo",
                              "extrato_pulados", "extrato_cortou",
                          "extrato_candidatas"):
                    st.session_state.pop(chave, None)
                st.rerun()
        conf2.markdown(
            f"<div class='apoio' style='padding-top:8px'>Somando as despesas marcadas: "
            f"<strong>{brl(total_marcado)}</strong>. Elas entram como "
            f"<em>{metodo_extrato}</em>.</div>",
            unsafe_allow_html=True,
        )

        if confirmar:
            importados = pulados = invalidos = 0
            for _, linha in marcados.iterrows():
                data_ = pd.to_datetime(linha["data"], errors="coerce")
                descricao_lida = str(linha["descricao"] or "").strip()
                valor_lido = float(linha["valor"] or 0)
                if pd.isna(data_) or not descricao_lida or valor_lido <= 0:
                    invalidos += 1
                    continue
                data_txt = data_.strftime("%Y-%m-%d")
                if db.lancamento_existe(data_txt, descricao_lida, valor_lido):
                    pulados += 1
                    continue
                db.inserir_lancamento(
                    data_txt, descricao_lida,
                    linha["categoria"] or CATEGORIA_NAO_ATRIBUIDA,
                    linha["tipo"] or "despesa", valor_lido, metodo_extrato,
                    False, "Importado da fatura em PDF",
                )
                importados += 1

            for chave in ("extrato_lido", "extrato_arquivo", "extrato_paginas",
                          "extrato_diagnostico", "extrato_metodo",
                          "extrato_pulados", "extrato_cortou",
                          "extrato_candidatas"):
                st.session_state.pop(chave, None)
            partes = [f"{importados} importado(s)"]
            if pulados:
                partes.append(f"{pulados} repetido(s) ignorado(s)")
            if invalidos:
                partes.append(f"{invalidos} linha(s) incompleta(s)")
            st.toast(" · ".join(partes), icon="📄")
            st.rerun()

# =============================================================== orçamento

with aba_orc:
    orcamentos = db.listar_orcamentos()
    gasto_por_cat = (df_mes[df_mes["tipo"] == "despesa"]
                     .groupby("categoria")["valor"].sum().to_dict())
    despesas_cat = categorias[categorias["tipo"] == "despesa"]["nome"].tolist()

    col_barras, col_form = st.columns([1.6, 1], gap="large")

    with col_barras:
        st.markdown(
            "<div class='secao'>Quanto de cada limite já foi usado</div>",
            unsafe_allow_html=True,
        )
        ativos = [c for c in despesas_cat if orcamentos.get(c)]
        if not ativos:
            st.info("Defina um limite ao lado para acompanhar suas metas por categoria.")
        else:
            ritmo = (dias_corridos / dias_no_mes) * 100
            blocos = []
            for nome in sorted(ativos, key=lambda c: -(gasto_por_cat.get(c, 0) / orcamentos[c])):
                limite = orcamentos[nome]
                gasto = gasto_por_cat.get(nome, 0.0)
                uso = gasto / limite * 100
                # a barra escurece conforme aperta: acento (folgado) →
                # neutro médio (no limite) → neutro forte (estourou)
                if uso >= 100:
                    cor, nota = TEMA["texto"], f"Estourou {brl(gasto - limite)}."
                elif uso >= 80:
                    cor, nota = TEMA["saida"], f"Restam {brl(limite - gasto)} até o limite."
                else:
                    cor, nota = TEMA["entrada"], f"Restam {brl(limite - gasto)} até o limite."
                blocos.append(
                    f"""<div class='orc'>
                        <div class='orc-topo'>
                            <span>{icones.get(nome, '')} {nome}</span>
                            <span class='orc-valor'>{brl(gasto)} de {brl(limite)}</span>
                        </div>
                        <div class='trilho'>
                            <div class='preenchido' style='width:{min(uso, 100):.1f}%;
                                 background:{cor}'></div>
                            <div class='marca' style='left:{min(ritmo, 100):.1f}%'></div>
                        </div>
                        <div class='orc-nota'>{nota} {pct(uso)} usado — a marca mostra
                        onde você deveria estar no dia {dias_corridos}.</div>
                    </div>"""
                )
            st.markdown("".join(blocos), unsafe_allow_html=True)

            total_limite = sum(orcamentos[c] for c in ativos)
            total_gasto = sum(gasto_por_cat.get(c, 0) for c in ativos)
            st.markdown(
                cartao("Somando as categorias com limite",
                       f"{brl(total_gasto)} de {brl(total_limite)}",
                       "saida" if total_gasto > total_limite else "entrada"),
                unsafe_allow_html=True,
            )

    with col_form:
        st.markdown("<div class='secao'>Definir limites</div>", unsafe_allow_html=True)
        tabela_orc = pd.DataFrame({
            "categoria": despesas_cat,
            "limite": [float(orcamentos.get(c, 0.0)) for c in despesas_cat],
        })
        editado_orc = st.data_editor(
            tabela_orc, hide_index=True, width="stretch", height=430,
            key="editor_orcamento",
            column_config={
                "categoria": st.column_config.TextColumn("Categoria", disabled=True),
                "limite": st.column_config.NumberColumn(
                    "Limite mensal", format="R$ %.2f", min_value=0.0, step=50.0),
            },
        )
        if st.button("Salvar limites", type="primary"):
            for _, linha in editado_orc.iterrows():
                db.salvar_orcamento(linha["categoria"], float(linha["limite"] or 0))
            st.toast("Limites salvos.", icon="🎯")
            st.rerun()
        st.markdown(
            "<div class='apoio'>Deixe em R$ 0,00 para não acompanhar a categoria.</div>",
            unsafe_allow_html=True,
        )

# ================================================================ ajustes

with aba_ajustes:
    col_cat, col_dados = st.columns(2, gap="large")

    with col_cat:
        st.markdown("<div class='secao'>Categorias</div>", unsafe_allow_html=True)

        with st.form("form_categoria", border=False):
            nome_cat = st.text_input("Nome", placeholder="Pet, Viagem, Mesada…")
            linha_a, linha_b, linha_c = st.columns([2, 1, 1])
            tipo_cat = linha_a.selectbox("Tipo", TIPOS, format_func=str.capitalize)
            icone_cat = linha_b.text_input("Ícone", value="📦", max_chars=2)
            cor_cat = linha_c.color_picker("Cor", value="#8A9AAB")
            if st.form_submit_button("Salvar categoria"):
                if nome_cat.strip():
                    db.salvar_categoria(nome_cat, tipo_cat, cor_cat, icone_cat or "📦")
                    st.toast(f"Categoria {nome_cat} salva.", icon="🏷️")
                    st.rerun()
                else:
                    st.warning("Dê um nome para a categoria.")

        chips = []
        for _, linha in categorias.iterrows():
            chips.append(
                f"<span class='chip'><i style='background:{linha['cor']}'></i>"
                f"{linha['icone']} {linha['nome']}</span>"
            )
        st.markdown("".join(chips), unsafe_allow_html=True)

        excluir_cat = st.selectbox("Remover categoria", ["—"] + categorias["nome"].tolist())
        if st.button("Remover") and excluir_cat != "—":
            em_uso = db.excluir_categoria(excluir_cat)
            if em_uso:
                st.warning(f"{excluir_cat} ainda tem {em_uso} lançamento(s). "
                           "Troque a categoria deles antes de remover.")
            else:
                st.toast(f"{excluir_cat} removida.", icon="🗑️")
                st.rerun()

    with col_dados:
        st.markdown("<div class='secao'>Seus dados</div>", unsafe_allow_html=True)

        arquivo = st.file_uploader(
            "Importar CSV", type=["csv"],
            help="Colunas necessárias: data, descricao, categoria, tipo, valor. "
                 "Opcionais: metodo, fixo, obs.",
        )
        if arquivo is not None and st.button("Importar agora", type="primary"):
            try:
                bruto = pd.read_csv(arquivo, sep=None, engine="python")
                importados, avisos = db.importar_dataframe(bruto)
                if importados:
                    st.success(f"{importados} lançamento(s) importado(s).")
                for aviso in avisos[:5]:
                    st.warning(aviso)
                if importados:
                    st.rerun()
            except Exception as erro:
                st.error(f"Não deu para ler o arquivo: {erro}")

        st.download_button("Baixar tudo em CSV", db.exportar_csv(),
                           file_name="lancamentos.csv", mime="text/csv")

        st.divider()
        if df_todos.empty:
            st.markdown(
                "<div class='apoio'>Ainda não há lançamentos. Você pode gerar seis meses "
                "de dados fictícios para explorar o dashboard e depois apagar tudo.</div>",
                unsafe_allow_html=True,
            )
            if st.button("Gerar dados de exemplo"):
                total = db.popular_exemplo()
                st.toast(f"{total} lançamentos de exemplo criados.", icon="✨")
                st.rerun()
        else:
            confirma = st.checkbox("Quero apagar todos os lançamentos e limites")
            if st.button("Apagar tudo", disabled=not confirma):
                db.apagar_tudo()
                st.toast("Base zerada.", icon="🧹")
                st.rerun()
