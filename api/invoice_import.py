import io
import re
from datetime import date as date_type
from typing import List, Optional

import pdfplumber
from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from pdfminer.pdfdocument import PDFPasswordIncorrect

from models import ParsedTransaction

router = APIRouter(tags=["imports"])

# Casa linhas no formato "DD/MM[/AAAA]  Descrição da compra          1.234,56"
# — usado por bancos como Itaú, Bradesco, Nubank.
NUMERIC_DATE_PATTERN = re.compile(
    r"^\s*(?P<day>\d{2})/(?P<month>\d{2})(?:/(?P<year>\d{2,4}))?\s+"
    r"(?P<description>.+?)\s+"
    r"(?P<amount>-?\d{1,3}(?:\.\d{3})*,\d{2})\s*$"
)

# Casa linhas no formato "01 de jul. 2026  Descrição da compra  - R$ 1.234,56"
# — usado pelo Banco Inter. Pagamentos/estornos trazem um "+" extra: "- + R$ 897,14".
MONTH_ABBREVIATIONS = {
    "jan": 1, "fev": 2, "mar": 3, "abr": 4, "mai": 5, "jun": 6,
    "jul": 7, "ago": 8, "set": 9, "out": 10, "nov": 11, "dez": 12,
}
NAMED_MONTH_PATTERN = re.compile(
    r"^(?P<day>\d{2}) de (?P<month>[a-z]{3})\.?\s+(?P<year>\d{4})\s+"
    r"(?P<description>.+?)\s+-\s*(?P<sign>\+)?\s*R\$\s*(?P<amount>\d{1,3}(?:\.\d{3})*,\d{2})\s*$",
    re.IGNORECASE,
)

# Linhas de resumo da fatura (saldo, limite, total) não são lançamentos.
IGNORED_KEYWORDS = (
    "SALDO ANTERIOR",
    "TOTAL DESTA FATURA",
    "TOTAL DA FATURA",
    "LIMITE DISPONIVEL",
    "LIMITE DE CREDITO",
    "ENCARGOS",
)

CATEGORY_KEYWORDS = {
    "Transporte": ["UBER", "99APP", "99POP", "POSTO", "COMBUSTIVEL", "ESTACIONAMENTO", "PEDAGIO"],
    "Alimentação": [
        "IFOOD", "IFD*", "MERCADO", "SUPERMERCADO", "RESTAURANTE", "PADARIA", "LANCHONETE", "ACOUGUE",
        "BAR ", "PIZZARIA", "BURGER", "MC DONALDS",
    ],
    "Assinaturas": ["NETFLIX", "SPOTIFY", "PRIME VIDEO", "DISNEY", "HBO", "YOUTUBE PREMIUM", "ICLOUD"],
    "Saúde": ["FARMACIA", "DROGARIA", "DROGASIL", "HOSPITAL", "CLINICA", "LABORATORIO"],
    "Compras": ["MERCADO LIVRE", "SHOPEE", "MAGAZINE LUIZA", "AMAZON", "SHEIN", "ALIEXPRESS"],
    "Lazer": ["CINEMARK", "CINEMA", "INGRESSO"],
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


def _build_transaction(
    transaction_date: date_type, raw_description: str, amount: float, is_credit: bool
) -> Optional[ParsedTransaction]:
    description = re.sub(r"\s{2,}", " ", raw_description).strip()
    if not description:
        return None
    return ParsedTransaction(
        date=transaction_date,
        description=description,
        amount=abs(amount),
        category=_guess_category(description),
        is_credit=is_credit,
        include=not is_credit,
    )


def _try_parse_named_month_line(line: str) -> Optional[ParsedTransaction]:
    match = NAMED_MONTH_PATTERN.match(line)
    if not match:
        return None

    month = MONTH_ABBREVIATIONS.get(match.group("month").lower())
    if month is None:
        return None

    try:
        transaction_date = date_type(int(match.group("year")), month, int(match.group("day")))
    except ValueError:
        return None

    amount = _parse_amount(match.group("amount"))
    is_credit = bool(match.group("sign"))
    return _build_transaction(transaction_date, match.group("description"), amount, is_credit)


def _try_parse_numeric_date_line(
    line: str, reference_year: int, reference_month: int
) -> Optional[ParsedTransaction]:
    match = NUMERIC_DATE_PATTERN.match(line)
    if not match:
        return None

    try:
        raw_amount = _parse_amount(match.group("amount"))
        day = int(match.group("day"))
        month = int(match.group("month"))
        year = _resolve_year(month, match.group("year"), reference_year, reference_month)
        transaction_date = date_type(year, month, day)
    except ValueError:
        return None

    return _build_transaction(transaction_date, match.group("description"), raw_amount, raw_amount < 0)


def parse_statement_text(text: str, reference_year: int, reference_month: int) -> List[ParsedTransaction]:
    transactions: List[ParsedTransaction] = []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if any(keyword in line.upper() for keyword in IGNORED_KEYWORDS):
            continue

        transaction = _try_parse_named_month_line(line) or _try_parse_numeric_date_line(
            line, reference_year, reference_month
        )
        if transaction:
            transactions.append(transaction)

    return transactions


@router.post("/imports/parse", response_model=List[ParsedTransaction])
async def parse_invoice(
    file: UploadFile = File(...),
    reference_year: int = Form(...),
    reference_month: int = Form(..., ge=1, le=12),
    password: Optional[str] = Form(None),
):
    if file.content_type != "application/pdf" and not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Envie um arquivo PDF")

    content = await file.read()
    try:
        with pdfplumber.open(io.BytesIO(content), password=password or "") as pdf:
            text = "\n".join(page.extract_text() or "" for page in pdf.pages)
    except PDFPasswordIncorrect as exc:
        detail = (
            "Senha incorreta para este PDF."
            if password
            else "Este PDF está protegido por senha. Informe a senha da fatura (geralmente os primeiros "
            "dígitos do CPF ou a data de nascimento — confira o e-mail ou app do seu banco)."
        )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail) from exc
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
