"""Rotas de autenticacao: cadastro, login e refresh."""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session, sessionmaker
from schemas import UsuarioSchema
from dependencies import pegar_sessao, verificar_refresh_token, verificar_token

from models import Usuario, db

from schemas import (
    LoginSchema,
    TokenResponse,
    UsuarioResponse,
    UsuarioSchema,
)
from security import criar_par_de_tokens, gerar_hash_senha, verificar_senha
from dependencies import pegar_sessao

auth_routes = APIRouter(prefix="/auth", tags=["auth"])

@auth_routes.get("/criar_conta")
async def criar_conta(usuario_schema: UsuarioSchema,session=Depends(pegar_sessao)):
        """busca o usuario e confere a senha"""
        Session = sessionmaker(bind=db)
        session = Session()
        usuario = session.query(Usuario).filter(Usuario.email==usuario_schema.email).first()
        if usuario:
            #já existe um usuário com o email
            raise HTTPException(status_code=400, detail="Já existe um usuário com este email!!!!!!")
        
        else:
            senha_criptografada = gerar_hash_senha(usuario_schema.senha)
            novo_usuario = Usuario(usuario_schema.nome,usuario_schema.email, senha_criptografada, usuario_schema.ativo, usuario_schema.admin)
            session.add(novo_usuario)
            session.commit()
            return{"Mensagem": f"Usuário Cadastrado com sucesso {usuario_schema.email}"}
        
@auth_routes.post("/criar_conta")
async def criar_conta(usuario_schema: UsuarioSchema,session=Depends(pegar_sessao)):
        """busca o usuario e confere a senha"""
     
        usuario = session.query(Usuario).filter(Usuario.email==usuario_schema.email).first()
        if usuario:
            #já existe um usuário com o email
            raise HTTPException(status_code=400, detail="Já existe um usuário com este email!!!!!!")
        
        else:
            senha_criptografada = gerar_hash_senha(usuario_schema.senha)
            novo_usuario = Usuario(usuario_schema.nome,usuario_schema.email, senha_criptografada, usuario_schema.ativo, usuario_schema.admin)
            session.add(novo_usuario)
            session.commit()
            return{"Mensagem": f"Usuário Cadastrado com sucesso {usuario_schema.email}"}
# autenticar(email: str, senha: str, session: Session) -> Usuario:
#     """Busca o usuario e confere a senha.

#     Mesma mensagem de erro para "e-mail nao existe" e "senha errada": entregar
#     erros diferentes deixa um atacante descobrir quais e-mails estao cadastrados.
#     """
#     usuario = session.query(Usuario).filter(Usuario.email == email).first()

#     if not usuario or not verificar_senha(senha, usuario.senha):
#         raise HTTPException(
#             status_code=status.HTTP_401_UNAUTHORIZED,
#             detail="Credenciais invalidas",
#         )

#     return usuario

# @auth_routes.post(
# "/criar_conta",
#     response_model=UsuarioResponse,
#     status_code=status.HTTP_201_CREATED,
# )
# async def criar_conta(
#     usuario_schema: UsuarioSchema,
#     session: Session = Depends(pegar_sessao),
# ):
#     """Cadastra um usuario novo. A senha vai para o banco como hash bcrypt."""
#     ja_existe = (
#         session.query(Usuario).filter(Usuario.email == usuario_schema.email).first()
#     )
#     if ja_existe:
#         raise HTTPException(
#             status_code=status.HTTP_400_BAD_REQUEST,
#             detail="Ja existe uma conta com esse e-mail",
#         )

#     novo_usuario = Usuario(
#         nome=usuario_schema.nome,
#         email=usuario_schema.email,
#         senha=gerar_hash_senha(usuario_schema.senha),
#         ativo=usuario_schema.ativo,
#         admin=usuario_schema.admin,
#     )
#     session.add(novo_usuario)
#     session.commit()
#     session.refresh(novo_usuario)

#     return novo_usuario


# @auth_routes.post("/login", response_model=TokenResponse)
# async def login(
#     login_schema: LoginSchema,
#     session: Session = Depends(pegar_sessao),
# ):
#     """Login via JSON. Devolve access token + refresh token."""
#     usuario = _autenticar(login_schema.email, login_schema.senha, session)
#     access_token, refresh_token = criar_par_de_tokens(usuario.id)

#     return TokenResponse(access_token=access_token, refresh_token=refresh_token)


# @auth_routes.post("/login-form", response_model=TokenResponse)
# async def login_form(
#     dados_form: OAuth2PasswordRequestForm = Depends(),
#     session: Session = Depends(pegar_sessao),
# ):
#     """Mesmo login, mas no formato `application/x-www-form-urlencoded` que o
#     padrao OAuth2 exige. E esta rota que o botao "Authorize" do /docs usa.

#     Detalhe: o form manda o campo como `username`, entao passamos ele como
#     e-mail.
#     """
#     usuario = _autenticar(dados_form.username, dados_form.password, session)
#     access_token, refresh_token = criar_par_de_tokens(usuario.id)

#     return TokenResponse(access_token=access_token, refresh_token=refresh_token)


# @auth_routes.post("/refresh", response_model=TokenResponse)
# async def usar_refresh_token(usuario: Usuario = Depends(verificar_refresh_token)):
#     """Troca um refresh token valido por um par novo, sem pedir a senha."""
#     access_token, refresh_token = criar_par_de_tokens(usuario.id)

#     return TokenResponse(access_token=access_token, refresh_token=refresh_token)


# @auth_routes.get("/eu", response_model=UsuarioResponse)
# async def quem_sou_eu(usuario: Usuario = Depends(verificar_token)):
#     """Rota de conferencia: se o token estiver valido, devolve o dono dele."""
#     return usuario
