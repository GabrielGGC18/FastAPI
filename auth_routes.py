"""Rotas de autenticacao: cadastro, login e refresh."""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import sessionmaker
from schemas import UsuarioSchema
from dependencies import pegar_sessao, verificar_refresh_token, verificar_token

from typing import Annotated
from sqlalchemy import select
from models import Usuario, db

from schemas import (
    LoginSchema,
    TokenResponse,
    UsuarioResponse,
    UsuarioSchema,
)
from security import criar_par_de_tokens, gerar_hash_senha, verificar_senha
from dependencies import pegar_sessao
from sqlalchemy.ext.asyncio import AsyncSession

auth_routes = APIRouter(prefix="/auth", tags=["auth"])

@auth_routes.post("/criar_conta", response_model=UsuarioResponse, status_code=status.HTTP_201_CREATED)
async def criar_conta(usuario_schema: UsuarioSchema, session: Annotated[AsyncSession, Depends(pegar_sessao)]):
    """Função para criar uma nova conta de usuário. A senha é armazenada como hash bcrypt."""
    usuario_existente = await session.scalar(select(Usuario).where(Usuario.email == usuario_schema.email))
    
    if usuario_existente:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Já Existe um usuário com esse e-mail",
        )
        
    novo_usuario = Usuario(
        nome=usuario_schema.nome,
        email=usuario_schema.email,
        senha=gerar_hash_senha(usuario_schema.senha),
        ativo=usuario_schema.ativo,
        admin=usuario_schema.admin,
    ) 
    session.add(novo_usuario)
    await session.commit()
    await session.refresh(novo_usuario)
    
    return novo_usuario
#Função privada para autenticar o usuário com base no e-mail. 
async def _autenticar(email: str, senha: str, session: AsyncSession) -> Usuario:
    """Busca o usuário e verifica a senha"""
    usuario =  await session.scalar(select(Usuario).where(Usuario.email == email))
    
    if not usuario or not verificar_senha(senha, usuario.senha):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciais inválidas",
        )
    return usuario

@auth_routes.post("/login", response_model=TokenResponse)
async def login(login_schema: LoginSchema, session: Annotated[AsyncSession, Depends(pegar_sessao)]):
    """Login via JSON. Devolvendo acess token + refresh token."""
    usuario = await _autenticar(login_schema.email, login_schema.senha, session)
    access_token, refresh_token = criar_par_de_tokens(usuario.id)
    
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)

@auth_routes.post("/refresh", response_model=TokenResponse)
async def refresh_token(usuario: Annotated[Usuario, Depends(verificar_refresh_token)]):
    """Recebe refresh token e devolve novo par de tokens."""
    par_de_tokens = criar_par_de_tokens(usuario.id)

    return TokenResponse(access_token=par_de_tokens[0], refresh_token=par_de_tokens[1])
    
    