from fastapi import FastAPI
from auth_routes import router as auth_router
from orders_routes import router as orders_router     

app = FastAPI()

app.include_router(auth_router)
app.include_router(orders_router)


# Para Rodar 
#Execute - uvicorn main:app --reload
#Rest APIs da Arquitetutura REST (Get, Post, Put/Patch, Delete) - 
# Create, Read, Update, Delete. - CRUD - É de operações para o banco de dados.
