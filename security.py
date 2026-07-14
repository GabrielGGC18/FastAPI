"""Hash de senha e emissao/leitura de JWT.

Nota sobre bcrypt: o curso costuma usar `passlib.CryptContext`, mas passlib 1.7.4
nao e compativel com bcrypt >= 4.1 (estoura `ValueError: password cannot be longer
than 72 bytes` ja na deteccao do backend). Aqui chamamos a lib `bcrypt` direto,
que e a mesma primitiva sem a camada quebrada em cima.
"""

import os
from datetime import datetime, timedelta, timezone

import bcrypt
from dotenv import load_dotenv
from jose import JWTError, jwt

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))

if not SECRET_KEY:
    raise RuntimeError(
        "SECRET_KEY nao definida. Copie .env.example para .env e gere uma chave "
        "com: python -c 'import secrets; print(secrets.token_hex(32))'"
    )

# bcrypt trunca em 72 bytes. Cortamos antes para nunca estourar ValueError.
BCRYPT_MAX_BYTES = 72


def _to_bytes(senha: str) -> bytes:
    return senha.encode("utf-8")[:BCRYPT_MAX_BYTES]


def gerar_hash_senha(senha: str) -> str:
    return bcrypt.hashpw(_to_bytes(senha), bcrypt.gensalt()).decode("utf-8")


def verificar_senha(senha: str, hash_armazenado: str) -> bool:
    return bcrypt.checkpw(_to_bytes(senha), hash_armazenado.encode("utf-8"))


def criar_token(
    id_usuario: int,
    duracao: timedelta | None = None,
    escopo: str = "access_token",
) -> str:
    """Monta um JWT.

    `sub` (subject) e uma claim padrao do JWT e precisa ser string.
    `exp` e a expiracao — a lib checa ela sozinha no decode.
    """
    if duracao is None:
        duracao = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    payload = {
        "sub": str(id_usuario),
        "exp": datetime.now(timezone.utc) + duracao,
        "scope": escopo,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def criar_par_de_tokens(id_usuario: int) -> tuple[str, str]:
    """Access token curto (usado a cada request) + refresh token longo.

    O refresh existe para o usuario nao ter que digitar a senha de novo quando
    o access expira: ele troca o refresh por um access novo.
    """
    access = criar_token(id_usuario)
    refresh = criar_token(
        id_usuario,
        duracao=timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
        escopo="refresh_token",
    )
    return access, refresh


def ler_token(token: str, escopo: str = "access_token") -> int:
    """Valida assinatura, expiracao e escopo. Devolve o id do usuario.

    Levanta `JWTError` se qualquer coisa estiver errada — quem chama traduz
    isso para um HTTP 401.
    """
    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])

    if payload.get("scope") != escopo:
        raise JWTError(f"Escopo invalido: esperado {escopo}")

    sub = payload.get("sub")
    if sub is None:
        raise JWTError("Token sem 'sub'")

    return int(sub)
