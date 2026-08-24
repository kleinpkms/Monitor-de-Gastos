import os
import sys

sys.path.append(os.path.dirname(__file__))

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from expenses import router as expenses_router
from invoice_import import router as invoice_import_router

app = FastAPI(title="Expense Tracker API", version="1.0.0")

allowed_origins = os.environ.get("CORS_ORIGINS", "*").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(expenses_router, prefix="/api")
app.include_router(invoice_import_router, prefix="/api")


@app.get("/api/health")
async def health():
    return {"status": "ok"}
