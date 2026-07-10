from fastapi import APIRouter

order_routes = APIRouter(prefix="/orders", tags=["orders"])

@order_router.get("/")
async def funcao():
    return {"Message: Rota Accessada com sucesso!"}
