import io
import re
from datetime import date as date_type
from typing import List, Optional

import pdfplumber
from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status

from models import ParsedTransaction

router = APIRouter(tags=["imports"])

# Casa linhas no formato "DD/MM[/AAAA]  Descrição da compra          1.234,56"
# — o padrão de layout usado pela maioria das faturas de cartão brasileiras.
LINE_PATTERN = re.compile(
    r"^\s*(?P<day>\d{2})/(?P<month>\d{2})(?:/(?P<year>\d{2,4}))?\s+"
    r"(?P<description>.+?)\s+"
    r"(?P<amount>-?\d{1,3}(?:\.\d{3})*,\d{2})\s*$"
)

# Linhas de resumo da fatura (saldo, limite, total) não são lançamentos.
IGNORED_KEYWORDS = (
    "SALDO ANTERIOR",
    "PAGAMENTO EFETUADO",
    "PAGTO DEBITO EM CONTA",
    "PAGAMENTO RECEBIDO",
    "TOTAL DESTA FATURA",
    "TOTAL DA FATURA",
    "LIMITE DISPONIVEL",
    "LIMITE DE CREDITO",
    "ENCARGOS",
)

CATEGORY_KEYWORDS = {
    "Transporte": ["UBER", "99APP", "99POP", "POSTO", "COMBUSTIVEL", "ESTACIONAMENTO", "PEDAGIO"],
    "Alimentação": ["IFOOD", "MERCADO", "SUPERMERCADO", "RESTAURANTE", "PADARIA", "LANCHONETE", "ACOUGUE"],
    "Assinaturas": ["NETFLIX", "SPOTIFY", "PRIME VIDEO", "DISNEY", "HBO", "YOUTUBE PREMIUM", "ICLOUD"],
    "Saúde": ["FARMACIA", "DROGARIA", "DROGASIL", "HOSPITAL", "CLINICA", "LABORATORIO"],
    "Compras": ["MERCADO LIVRE", "SHOPEE", "MAGAZINE LUIZA", "AMAZON", "SHEIN", "ALIEXPRESS"],
}


def _parse_amount(raw: str) -> float:
    normalized = raw.replace(".", "").replace(",", ".")
    return float(normalized)


def _resolve_year(month: int, year_hint: Optional[str], reference_year: int, reference_month: int) -> int:
    if year_hint:
        year = int(year_hint)
        return year if year > 100 else 2000 + year
    # Faturas costumam listar compras do período anterior ao fechamento; se o mês
    # do lançamento vier depois do mês de referência, ele pertence ao ano anterior
    # (ex.: fatura de referência jan/2026 com compras de dez/2025).
    if month > reference_month:
        return reference_year - 1
    return reference_year


def _guess_category(description: str) -> str:
    upper = description.upper()
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(keyword in upper for keyword in keywords):
            return category
    return ""


def parse_statement_text(text: str, reference_year: int, reference_month: int) -> List[ParsedTransaction]:
    transactions: List[ParsedTransaction] = []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if any(keyword in line.upper() for keyword in IGNORED_KEYWORDS):
            continue

        match = LINE_PATTERN.match(line)
        if not match:
            continue

        try:
            raw_amount = _parse_amount(match.group("amount"))
            day = int(match.group("day"))
            month = int(match.group("month"))
            year = _resolve_year(month, match.group("year"), reference_year, reference_month)
            transaction_date = date_type(year, month, day)
        except ValueError:
            continue

        description = re.sub(r"\s{2,}", " ", match.group("description")).strip()
        if not description:
            continue

        is_credit = raw_amount < 0
        transactions.append(
            ParsedTransaction(
                date=transaction_date,
                description=description,
                amount=abs(raw_amount),
                category=_guess_category(description),
                is_credit=is_credit,
                include=not is_credit,
            )
        )

    return transactions


@router.post("/imports/parse", response_model=List[ParsedTransaction])
async def parse_invoice(
    file: UploadFile = File(...),
    reference_year: int = Form(...),
    reference_month: int = Form(..., ge=1, le=12),
):
    if file.content_type != "application/pdf" and not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Envie um arquivo PDF")

    content = await file.read()
    try:
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            text = "\n".join(page.extract_text() or "" for page in pdf.pages)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Não foi possível ler o PDF enviado"
        ) from exc

    transactions = parse_statement_text(text, reference_year, reference_month)
    if not transactions:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Nenhum lançamento foi reconhecido neste PDF. O layout desta fatura pode não ser suportado — "
            "você ainda pode cadastrar os gastos manualmente.",
        )
    return transactions
