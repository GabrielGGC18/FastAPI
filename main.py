from fastapi import FastAPI
from auth_routes import auth_routes as auth_router
from orders_routes import order_routes as orders_routes    

app = FastAPI()

app.include_router(auth_router)
app.include_router(orders_routes)


# Para Rodar 
#Execute - uvicorn main:app --reload
#Rest APIs da Arquitetutura REST (Get, Post, Put/Patch, Delete) - 
# Create, Read, Update, Delete. - CRUD - É de operações para o banco de dados.
