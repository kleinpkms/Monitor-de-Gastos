"""
Login pelo Auth0, usando o `st.login()` nativo do Streamlit.

O Streamlit fala OpenID Connect desde a 1.42: ele leva a pessoa até o
provedor, valida o token de volta e guarda a sessão num cookie assinado
com o `cookie_secret`. Quem cuida de senha, "esqueci minha senha",
verificação de e-mail e "entrar com o Google" é o Auth0 — este projeto
nunca vê nem guarda senha de ninguém.

A configuração mora em `.streamlit/secrets.toml` (que está no .gitignore);
veja `secrets.toml.example` ao lado, e o README para o passo a passo no
painel do Auth0 e no Render.

O que o resto do app usa daqui:

    auth.exigir_login()   # no topo do app.py, antes de qualquer consulta
    auth.caixa_usuario()  # o rodapé da barra lateral, com o botão de sair
"""

from __future__ import annotations

import os

import streamlit as st

import database as db

# Nome do bloco `[auth.auth0]` no secrets.toml. Se você preferir a forma de
# provedor único (tudo solto em `[auth]`), também funciona: o `_provedor()`
# abaixo descobre qual dos dois você usou.
PROVEDOR = "auth0"

# Trava opcional: com `EMAILS_PERMITIDOS=a@x.com,b@y.com` no ambiente, só
# esses e-mails entram. Vazio (o padrão) deixa qualquer conta do seu tenant
# Auth0 criar o próprio dashboard, que é o normal.
EMAILS_PERMITIDOS = {
    e.strip().lower()
    for e in os.environ.get("EMAILS_PERMITIDOS", "").split(",")
    if e.strip()
}


# ------------------------------------------------------- configuração

def _bloco_auth():
    """O `[auth]` do secrets.toml, ou {} se não houver secrets nenhum."""
    try:
        return st.secrets.get("auth", {})
    except Exception:
        # Sem `.streamlit/secrets.toml`, versões mais antigas estouram em
        # vez de devolver vazio.
        return {}


def _provedor() -> str | None:
    """`"auth0"` se a configuração está aninhada; None se está solta em [auth]."""
    return PROVEDOR if PROVEDOR in _bloco_auth() else None


def _configurado() -> bool:
    auth = _bloco_auth()
    if not auth:
        return False
    bloco = auth.get(PROVEDOR, auth)
    return all(bloco.get(chave) for chave in
               ("client_id", "client_secret", "server_metadata_url"))


# ------------------------------------------------------------- telas

def _moldura(titulo: str, corpo: str):
    """Tela cheia, centralizada, no lugar do dashboard."""
    # A barra lateral nasce aberta (initial_sidebar_state no app.py) e aqui
    # ela ficaria vazia, porque o rerun para antes de montar os filtros —
    # uma faixa cinza sem nada ao lado do cartão de login.
    st.markdown(
        "<style>section[data-testid='stSidebar']{display:none}</style>",
        unsafe_allow_html=True,
    )
    st.markdown("<div style='height:12vh'></div>", unsafe_allow_html=True)
    _, meio, _ = st.columns([1, 1.25, 1])
    with meio:
        st.markdown(
            f"<div class='cartao'><div class='numero numero-medio'>◍ {titulo}</div>"
            f"<div class='apoio' style='margin-top:10px'>{corpo}</div></div>",
            unsafe_allow_html=True,
        )
        return meio


def _tela_login() -> None:
    meio = _moldura(
        "Suas finanças",
        "Entre para ver e lançar os seus gastos. Cada conta tem a própria "
        "base: lançamentos, categorias e limites não são compartilhados.",
    )
    with meio:
        st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)
        if st.button("Entrar", type="primary", width="stretch"):
            st.login(_provedor())
        st.markdown(
            "<div class='apoio' style='margin-top:12px'>Você é levado para a "
            "tela do Auth0, onde dá para usar e-mail e senha ou uma conta "
            "Google. A senha é registrada lá, nunca aqui.</div>",
            unsafe_allow_html=True,
        )


def _tela_sem_configuracao() -> None:
    _moldura(
        "Login não configurado",
        "Falta o bloco <code>[auth]</code> em <code>.streamlit/secrets.toml</code>. "
        "Copie o <code>secrets.toml.example</code> que está na raiz do projeto, "
        "preencha com os dados da sua aplicação no Auth0 e rode de novo — "
        "o README tem o passo a passo.",
    )


def _tela_sem_permissao(email: str) -> None:
    meio = _moldura(
        "Conta sem acesso",
        f"<code>{email or 'sua conta'}</code> não está na lista de e-mails "
        "liberados (<code>EMAILS_PERMITIDOS</code>) deste dashboard.",
    )
    with meio:
        st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)
        if st.button("Sair e tentar com outra conta", width="stretch"):
            st.logout()


# ------------------------------------------------------------ portão

def exigir_login() -> int:
    """Garante que há alguém logado e diz ao `database` de quem é a sessão.

    Devolve o id do usuário. Se ninguém entrou ainda, desenha a tela de
    login e encerra o rerun — nada abaixo da chamada chega a rodar.
    """
    if not _configurado():
        _tela_sem_configuracao()
        st.stop()

    if not st.user.is_logged_in:
        _tela_login()
        st.stop()

    # `st.user` é um Mapping com as claims do token; `.get` evita explodir
    # quando o tenant não manda um campo opcional.
    claims = dict(st.user)
    sub = claims.get("sub")
    email = (claims.get("email") or "").strip()
    nome = (claims.get("name") or claims.get("nickname") or "").strip()

    if not sub:
        # Sem identificador estável não dá para dizer de quem são as linhas.
        # Melhor parar do que arriscar misturar bases.
        _moldura(
            "Não deu para identificar a conta",
            "O token do Auth0 voltou sem o campo <code>sub</code>. Saia e "
            "entre de novo; se persistir, confira os escopos "
            "<code>openid profile email</code> na aplicação do Auth0.",
        )
        st.stop()

    if EMAILS_PERMITIDOS and email.lower() not in EMAILS_PERMITIDOS:
        _tela_sem_permissao(email)
        st.stop()

    # Uma ida ao banco por sessão, não por rerun: o id fica no session_state
    # e só é refeito se a pessoa trocar de conta na mesma aba.
    if st.session_state.get("_auth_sub") != sub:
        st.session_state["usuario_id"] = db.garantir_usuario(sub, email, nome)
        st.session_state["_auth_sub"] = sub

    usuario_id = st.session_state["usuario_id"]
    db.definir_usuario(usuario_id)  # o thread_local morre junto com o rerun
    return usuario_id


def caixa_usuario() -> None:
    """Quem está logado e o botão de sair. Vai no fim da barra lateral."""
    claims = dict(st.user)
    identificacao = (claims.get("name") or claims.get("email") or "conectado")
    email = claims.get("email") or ""

    st.markdown(
        f"<div class='apoio'><strong>{identificacao}</strong>"
        + (f"<br>{email}" if email and email != identificacao else "")
        + "</div>",
        unsafe_allow_html=True,
    )
    if st.button("Sair", width="stretch"):
        # Sem isso o id do usuário anterior sobreviveria ao logout nesta aba.
        for chave in ("usuario_id", "_auth_sub"):
            st.session_state.pop(chave, None)
        st.logout()
