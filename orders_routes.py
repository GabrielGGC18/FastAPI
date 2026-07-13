from fastapi import APIRouter

order_routes = APIRouter(prefix="/pedidos", tags=["orders"])

@order_routes.get("/")
async def pedidos():
    return {"Messagem": "Rota Accessada com sucesso!"}
