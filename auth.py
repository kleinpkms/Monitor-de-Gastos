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


CHAVES_PROVEDOR = ("client_id", "client_secret", "server_metadata_url")
_MARCAS_DE_EXEMPLO = ("SEU_", "SEU-", "troque", "o Client ", "COLE_", "AQUI")


def diagnosticar() -> list[str]:
    """O que falta para o login funcionar, chave por chave. Vazio = ok.

    Dizer "falta auth.auth0.client_id" poupa muito tempo em relação a um
    "login não configurado" genérico — ainda mais porque o erro mais comum
    não é chave errada, e sim o arquivo no lugar errado: o Streamlit
    procura `.streamlit/secrets.toml` a partir da pasta de onde você rodou
    o `streamlit run`, não da pasta do projeto.
    """
    auth = _bloco_auth()
    if not auth:
        return ["Não achei o bloco `[auth]`. Confira se existe "
                "`.streamlit/secrets.toml` **na pasta de onde você roda o "
                "`streamlit run`** e se o TOML está válido."]

    aninhado = PROVEDOR in auth
    bloco = auth.get(PROVEDOR, auth)
    prefixo = f"auth.{PROVEDOR}" if aninhado else "auth"
    problemas = [f"Falta `auth.{chave}`." for chave in ("redirect_uri", "cookie_secret")
                 if not auth.get(chave)]
    problemas += [f"Falta `{prefixo}.{chave}`." for chave in CHAVES_PROVEDOR
                  if not bloco.get(chave)]

    for chave in CHAVES_PROVEDOR:
        valor = str(bloco.get(chave) or "")
        if valor and any(m.lower() in valor.lower() for m in _MARCAS_DE_EXEMPLO):
            problemas.append(f"`{prefixo}.{chave}` ainda está com o texto de "
                             f"exemplo (`{valor[:34]}…`).")
    return problemas


def _configurado() -> bool:
    return not diagnosticar()


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
    def com_codigo(texto: str) -> str:
        partes = texto.split("`")
        return "".join(p if i % 2 == 0 else f"<code>{p}</code>"
                       for i, p in enumerate(partes))

    itens = "".join(f"<div style='margin-top:6px'>• {com_codigo(p)}</div>"
                    for p in diagnosticar())
    _moldura(
        "Login não configurado",
        f"Falta acertar o <code>.streamlit/secrets.toml</code>:{itens}"
        "<div style='margin-top:12px'>O <code>secrets.toml.example</code>, na raiz "
        "do projeto, tem o formato completo pronto para copiar; o README traz o "
        "passo a passo no painel do Auth0.</div>",
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
    st.session_state["usuario_email"] = email

    # Qual base esta sessão está olhando: a própria ou uma que alguém
    # compartilhou. A escolha vive no session_state (o seletor fica na
    # barra lateral, em `caixa_usuario`), mas é sempre reconferida contra o
    # banco — a tela não manda no acesso.
    base_id = st.session_state.get("base_ativa", usuario_id)
    if base_id != usuario_id and not db.pode_abrir_base(usuario_id, email, base_id):
        base_id = usuario_id
    st.session_state["base_ativa"] = base_id

    db.definir_usuario(base_id)  # o thread_local morre junto com o rerun
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

    # Seletor de base: só aparece para quem tem mais de uma (ou seja, para
    # quem recebeu um compartilhamento).
    usuario_id = st.session_state.get("usuario_id")
    if usuario_id is not None:
        bases = db.bases_visiveis(usuario_id, email)
        if len(bases) > 1:
            ids = [b["id"] for b in bases]
            rotulos = {b["id"]: b["rotulo"] for b in bases}
            atual = st.session_state.get("base_ativa", usuario_id)
            escolhida = st.selectbox(
                "Base em uso", ids,
                index=ids.index(atual) if atual in ids else 0,
                format_func=lambda i: rotulos[i], key="seletor_base",
            )
            if escolhida != st.session_state.get("base_ativa"):
                st.session_state["base_ativa"] = escolhida
                st.rerun()
            if escolhida != usuario_id:
                st.markdown(
                    f"<div class='apoio'>Você está editando a "
                    f"<strong>{rotulos[escolhida].lower()}</strong>. O que você "
                    "lançar aqui aparece para quem compartilhou.</div>",
                    unsafe_allow_html=True,
                )

    if st.button("Sair", width="stretch"):
        # Sem isso o id do usuário anterior sobreviveria ao logout nesta aba.
        for chave in ("usuario_id", "_auth_sub", "base_ativa", "usuario_email"):
            st.session_state.pop(chave, None)
        st.logout()
