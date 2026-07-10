from fastapi import APIRouter

order_routes = APIRouter(prefix="/orders", tags=["orders"])

@order_router.get("/lista")
def funcao():