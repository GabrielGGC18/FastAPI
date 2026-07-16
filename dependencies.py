"""Dependencias injetaveis (`Depends`).

Uma dependencia e so uma funcao que o FastAPI chama antes da rota e cujo
retorno ele entrega como argumento. Serve para nao repetir "abre sessao",
"valida token", "confere se e admin" em toda rota.
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy.orm import Session, sessionmaker

from models import Usuario, db
from security import ler_token

# Diz ao FastAPI onde fica a rota de login. Isso e o que faz aparecer o botao
# "Authorize" no /docs.
oauth2_schema = OAuth2PasswordBearer(tokenUrl="auth/login-form")

SessionLocal = sessionmaker(bind=db, autoflush=False, expire_on_commit=False)


def pegar_sessao():
    """Abre uma sessao por request e garante o fechamento no final.

    O `yield` faz disso um generator dependency: o que vem depois dele roda
    quando a resposta ja foi enviada — inclusive se a rota lancou excecao.
    """
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def _usuario_do_token(token: str, session: Session, escopo: str) -> Usuario:
    credenciais_invalidas = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token invalido ou expirado",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        id_usuario = ler_token(token, escopo=escopo)
    except JWTError:
        raise credenciais_invalidas

    usuario = session.query(Usuario).filter(Usuario.id == id_usuario).first()
    if usuario is None:
        raise credenciais_invalidas
    if not usuario.ativo:
        raise HTTPException(
            
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Conta desativada",
        )

    return usuario


def verificar_token(
    token: str = Depends(oauth2_schema),
    session: Session = Depends(pegar_sessao),
) -> Usuario:
    """Traduz o header `Authorization: Bearer <token>` no usuario logado."""
    return _usuario_do_token(token, session, escopo="access_token")


def verificar_refresh_token(
    token: str = Depends(oauth2_schema),
    session: Session = Depends(pegar_sessao),
) -> Usuario:
    """Igual, mas so aceita token de escopo `refresh_token`.

    Separar os escopos importa: se o access token vazar num log, ele expira em
    30 min. Se ele pudesse ser usado para gerar tokens novos, o vazamento
    viraria acesso eterno.
    """
    return _usuario_do_token(token, session, escopo="refresh_token")


def verificar_admin(usuario: Usuario = Depends(verificar_token)) -> Usuario:
    """Dependencia empilhada: reaproveita `verificar_token` e so adiciona a
    checagem de admin. Use em rotas que so administrador pode chamar."""
    if not usuario.admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acao permitida apenas para administradores",
        )
    return usuario
