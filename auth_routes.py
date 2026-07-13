from fastapi import APIRouter

auth_routes = APIRouter(prefix="/auth", tags=["auth"])

@auth_routes.get("/auth")
async def auth():
    return {"Mensagem:" "Autenticacao" "autenticado": False}