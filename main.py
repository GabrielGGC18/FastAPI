"""Ponto de entrada da API.

Rodar:  uvicorn main:app --reload
Docs:   http://127.0.0.1:8000/docs
"""

from fastapi import FastAPI

from auth_routes import criar_conta, auth_routes
from models import criar_banco
from orders_routes import order_routes

app = FastAPI(
    title="API de Pedidos",
    description="Projeto de estudo: FastAPI + SQLAlchemy + JWT.",
    version="0.2.0",
)

# Em producao isso vira migration (Alembic). Para estudo, criar na subida basta.
criar_banco()

app.include_router(auth_routes)
app.include_router(order_routes)


@app.get("/", tags=["health"])
async def home():
    return {"mensagem": "API no ar", "docs": "/docs"}
