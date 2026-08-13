"""Ponto de entrada da API.

Rodar:  uvicorn main:app --reload
Docs:   http://127.0.0.1:8000/docs
"""

import logging
import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from auth_routes import criar_conta, auth_routes
# from models import criar_banco -Já usando alembic, nao precisa mais criar banco na subida.
from orders_routes import order_routes

logger = logging.getLogger("api")

app = FastAPI(
    title="API de Pedidos",
    description="Projeto de estudo: FastAPI + SQLAlchemy + JWT.",
    version="0.2.0",
)

# Origens liberadas via env (CSV). Sem isso, front em outro dominio apanha do
# navegador antes mesmo de chegar na API.
_origins = os.getenv("CORS_ORIGINS", "")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def erro_nao_tratado(request: Request, exc: Exception):
    """Rede de seguranca: qualquer excecao nao prevista cai aqui em vez de
    vazar stacktrace pro cliente. O detalhe real vai so pro log."""
    logger.exception("Erro nao tratado em %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Erro interno do servidor"},
    )


# Em producao isso vira migration (Alembic). Para estudo, criar na subida basta.
# criar_banco() - Não precisa mais criar banco na subida, já que estamos usando alembic.

app.include_router(auth_routes)
app.include_router(order_routes)

SECRET_KEY = os.getenv("SECRET_KEY")


@app.get("/", tags=["health"])
async def home():
    return {"mensagem": "API no ar", "docs": "/docs"}
