"""Modelagem de dados da API de pedidos.

Diagrama (1:N em cascata):

    Usuario 1 ----< N Pedido 1 ----< N ItemPedido

- Um usuario faz varios pedidos.
- Um pedido tem varios itens.
- O preco do pedido e derivado: soma de (preco_unitario * quantidade) dos itens.
"""

import enum

from sqlalchemy import (
    Boolean,
    Column,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    create_engine,
)
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy_utils import ChoiceType
from settings import Settings

# Conexao com o banco. `echo=False` para nao poluir o terminal;
# troque para True quando quiser ver o SQL que o SQLAlchemy gera.
settings = Settings()
db = create_engine("sqlite:///banco.db", echo=False)
# Base declarativa: toda classe que herda dela vira uma tabela.
Base = declarative_base()


class StatusPedido(str, enum.Enum):
    """Estados possiveis de um pedido.

    Herdar de `str` faz o valor serializar como texto puro no JSON
    da resposta, em vez de virar um objeto.
    """

    PENDENTE = "PENDENTE"
    CANCELADO = "CANCELADO"
    FINALIZADO = "FINALIZADO"


class Usuario(Base):
    __tablename__ = "usuarios"

    id = Column("id", Integer, primary_key=True, autoincrement=True)
    nome = Column("nome", String, nullable=False)
    email = Column("email", String, nullable=False, unique=True, index=True)
    senha = Column("senha", String, nullable=False)  # guarda o hash, nunca o texto puro
    ativo = Column("ativo", Boolean, default=True)
    admin = Column("admin", Boolean, default=False)

    # Lado "um" do relacionamento 1:N. `back_populates` liga os dois lados,
    # entao `usuario.pedidos` e `pedido.usuario` ficam sempre em sincronia.
    pedidos = relationship(
        "Pedido",
        back_populates="usuario",
        cascade="all, delete-orphan",
    )

    def __init__(self, nome, email, senha, ativo=True, admin=False):
        self.nome = nome
        self.email = email
        self.senha = senha
        self.ativo = ativo
        self.admin = admin
        
class Pedido(Base):
    __tablename__ = "pedidos"

    id = Column("id", Integer, primary_key=True, autoincrement=True)
    # Enum no lugar de String: o banco passa a rejeitar status invalido.
    status = Column(
        "status",
        Enum(StatusPedido),
        default=StatusPedido.PENDENTE,
        nullable=False,
    )
    usuario_id = Column("usuario_id", Integer, ForeignKey("usuarios.id"), nullable=False)
    preco = Column("preco", Float, default=0.0)

    usuario = relationship("Usuario", back_populates="pedidos")
    itens = relationship(
        "ItemPedido",
        back_populates="pedido",
        cascade="all, delete-orphan",  # apagar o pedido apaga os itens junto
    )

    def __init__(self, usuario_id, status=StatusPedido.PENDENTE, preco=0.0):
        self.usuario_id = usuario_id
        self.status = status
        self.preco = preco

    def calcular_preco(self):
        """Recalcula o total a partir dos itens.

        Preco e dado derivado: nunca aceite ele do cliente, sempre recalcule
        no servidor apos qualquer mudanca na lista de itens.
        """
        self.preco = sum(item.preco_unitario * item.quantidade for item in self.itens)
        return self.preco


class ItemPedido(Base):
    __tablename__ = "itens_pedido"

    id = Column("id", Integer, primary_key=True, autoincrement=True)
    quantidade = Column("quantidade", Integer, nullable=False)
    sabor = Column("sabor", String, nullable=False)
    tamanho = Column("tamanho", String, nullable=False)
    preco_unitario = Column("preco_unitario", Float, nullable=False)
    pedido_id = Column("pedido_id", Integer, ForeignKey("pedidos.id"), nullable=False)

    # Guardamos o preco no momento da compra: se a pizzaria reajustar a tabela
    # amanha, o pedido de hoje continua valendo o preco de hoje.
    pedido = relationship("Pedido", back_populates="itens")

    def __init__(self, quantidade, sabor, tamanho, preco_unitario, pedido_id):
        self.quantidade = quantidade
        self.sabor = sabor
        self.tamanho = tamanho
        self.preco_unitario = preco_unitario
        self.pedido_id = pedido_id


def criar_banco():
    """Cria as tabelas que ainda nao existem.

    Nao altera tabelas ja criadas: se voce mudar uma coluna depois, precisa
    apagar `banco.db` ou usar Alembic (migrations). Ver docs/modelagem-de-dados.md.
    """
    Base.metadata.create_all(bind=db)


if __name__ == "__main__":
    criar_banco()
    print("Banco criado em banco.db")
