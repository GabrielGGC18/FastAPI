"""Schemas Pydantic: o contrato de entrada e saida da API.

Regra pratica: os models (SQLAlchemy) descrevem o BANCO, os schemas (Pydantic)
descrevem a API. Nunca devolva um model direto sem passar por um schema de
resposta, senao voce vaza campos que o cliente nao deveria ver (ex: `senha`).
"""

from typing import Optional

from pydantic import BaseModel, EmailStr, Field

from models import StatusPedido

# ---------------------------------------------------------------- Usuario
class UsuarioSchema(BaseModel):
    """Como o usuario entra na API. Repare: nao tem o campo `id`"""
    nome: str
    email: str
    senha: str = Field(..., min_length=6, description="Senha precisa ter pelo menos 6 caracteres")
    ativo : Optional[bool] = True
    admin: Optional[bool] = False
    
    class Config:
        model_config = True
class UsuarioResponse(BaseModel):
    """Como o usuario sai da API. Repare: nao tem o campo `senha`."""

    id: int
    nome: str
    email: EmailStr
    ativo: bool
    admin: bool

    # Permite construir o schema a partir de um objeto SQLAlchemy
    # (le atributos, nao chaves de dict).
    model_config = {"from_attributes": True}


class LoginSchema(BaseModel):
    email: EmailStr
    senha: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


# ---------------------------------------------------------------- Pedido


class ItemPedidoSchema(BaseModel):
    quantidade: int = Field(gt=0, description="Precisa ser pelo menos 1")
    sabor: str
    tamanho: str
    preco_unitario: float = Field(gt=0)

    model_config = {"from_attributes": True}


class ItemPedidoResponse(ItemPedidoSchema):
    id: int


class PedidoSchema(BaseModel):
    """Criacao de pedido.

    `usuario_id` e opcional: se vier vazio, a rota usa o usuario do token.
    So um admin consegue criar pedido em nome de outra pessoa.
    """

    usuario_id: Optional[int] = None

    model_config = {"from_attributes": True}


class PedidoResponse(BaseModel):
    id: int
    status: StatusPedido
    preco: float
    usuario_id: int
    itens: list[ItemPedidoResponse] = []

    model_config = {"from_attributes": True}


class ResponseMensagem(BaseModel):
    mensagem: str

class FilterPage(BaseModel):
    offset: int = Field(0, ge=0)
    limit: int = Field(100, le=100)
    