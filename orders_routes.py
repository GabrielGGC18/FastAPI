"""Rotas de pedido: CRUD + itens + transicoes de status.

Regra de autorizacao que se repete aqui: um usuario comum so enxerga e mexe nos
proprios pedidos; um admin mexe em qualquer um. Isso esta centralizado em
`_pedido_autorizado` para nao ficar espalhado por seis rotas.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from dependencies import pegar_sessao, verificar_token
from models import ItemPedido, Pedido, StatusPedido, Usuario
from schemas import (
    ItemPedidoSchema,
    PedidoResponse,
    PedidoSchema,
    ResponseMensagem,
)

order_routes = APIRouter(
    prefix="/pedidos",
    tags=["pedidos"],
    # Dependencia no router inteiro: nenhuma rota daqui roda sem token valido.
    dependencies=[Depends(verificar_token)],
)
@order_routes.post("/", response_model=PedidoResponse, status_code=status.HTTP_201_CREATED)
async def criar_pedido(
    pedido_schema: PedidoSchema,
    session: Session = Depends(pegar_sessao),
    usuario: Usuario = Depends(verificar_token),
):
    """Cria pedido vazio (status PENDENTE, preco 0). Itens entram depois."""
    dono_id = pedido_schema.usuario_id or usuario.id

    if dono_id != usuario.id and not usuario.admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="So um admin cria pedido em nome de outro usuario",
        )

    novo_pedido = Pedido(usuario_id=dono_id)
    session.add(novo_pedido)
    session.commit()
    session.refresh(novo_pedido)

    return novo_pedido



# def _pedido_autorizado(
#     id_pedido: int,
#     session: Session,
#     usuario: Usuario,
# ) -> Pedido:
#     """Busca o pedido e confere se `usuario` pode toca-lo."""
#     pedido = session.query(Pedido).filter(Pedido.id == id_pedido).first()

#     if not pedido:
#         raise HTTPException(
#             status_code=status.HTTP_404_NOT_FOUND,
#             detail="Pedido nao encontrado",
#         )

#     if not usuario.admin and pedido.usuario_id != usuario.id:
#         raise HTTPException(
#             status_code=status.HTTP_403_FORBIDDEN,
#             detail="Voce nao tem permissao sobre este pedido",
#         )

#     return pedido


# def _exigir_pendente(pedido: Pedido) -> None:
#     """Pedido cancelado ou finalizado e imutavel."""
#     if pedido.status != StatusPedido.PENDENTE:
#         raise HTTPException(
#             status_code=status.HTTP_400_BAD_REQUEST,
#             detail=f"Pedido {pedido.status.value} nao pode mais ser alterado",
#         )


# @order_routes.post(
#     "/",
#     response_model=PedidoResponse,
#     status_code=status.HTTP_201_CREATED,
# )
# async def criar_pedido(
#     pedido_schema: PedidoSchema,
#     session: Session = Depends(pegar_sessao),
#     usuario: Usuario = Depends(verificar_token),
# ):
#     """Cria pedido vazio (status PENDENTE, preco 0). Itens entram depois."""
#     dono_id = pedido_schema.usuario_id or usuario.id

#     if dono_id != usuario.id and not usuario.admin:
#         raise HTTPException(
#             status_code=status.HTTP_403_FORBIDDEN,
#             detail="So um admin cria pedido em nome de outro usuario",
#         )

#     novo_pedido = Pedido(usuario_id=dono_id)
#     session.add(novo_pedido)
#     session.commit()
#     session.refresh(novo_pedido)

#     return novo_pedido


# @order_routes.get("/", response_model=list[PedidoResponse])
# async def listar_pedidos(
#     session: Session = Depends(pegar_sessao),
#     usuario: Usuario = Depends(verificar_token),
# ):
#     """Admin ve tudo; usuario comum ve so os pedidos dele."""
#     query = session.query(Pedido)

#     if not usuario.admin:
#         query = query.filter(Pedido.usuario_id == usuario.id)

#     return query.all()


# @order_routes.get("/{id_pedido}", response_model=PedidoResponse)
# async def visualizar_pedido(
#     id_pedido: int,
#     session: Session = Depends(pegar_sessao),
#     usuario: Usuario = Depends(verificar_token),
# ):
#     return _pedido_autorizado(id_pedido, session, usuario)


# @order_routes.post("/{id_pedido}/itens", response_model=PedidoResponse)
# async def adicionar_item(
#     id_pedido: int,
#     item_schema: ItemPedidoSchema,
#     session: Session = Depends(pegar_sessao),
#     usuario: Usuario = Depends(verificar_token),
# ):
#     """Adiciona item e recalcula o total do pedido."""
#     pedido = _pedido_autorizado(id_pedido, session, usuario)
#     _exigir_pendente(pedido)

#     item = ItemPedido(
#         quantidade=item_schema.quantidade,
#         sabor=item_schema.sabor,
#         tamanho=item_schema.tamanho,
#         preco_unitario=item_schema.preco_unitario,
#         pedido_id=pedido.id,
#     )
#     session.add(item)
#     session.flush()  # empurra o INSERT para o banco sem fechar a transacao,
#     session.refresh(pedido)  # assim `pedido.itens` ja enxerga o item novo

#     pedido.calcular_preco()
#     session.commit()
#     session.refresh(pedido)

#     return pedido


# @order_routes.delete("/itens/{id_item}", response_model=PedidoResponse)
# async def remover_item(
#     id_item: int,
#     session: Session = Depends(pegar_sessao),
#     usuario: Usuario = Depends(verificar_token),
# ):
#     item = session.query(ItemPedido).filter(ItemPedido.id == id_item).first()
#     if not item:
#         raise HTTPException(
#             status_code=status.HTTP_404_NOT_FOUND,
#             detail="Item nao encontrado",
#         )

#     pedido = _pedido_autorizado(item.pedido_id, session, usuario)
#     _exigir_pendente(pedido)

#     session.delete(item)
#     session.flush()
#     session.refresh(pedido)

#     pedido.calcular_preco()
#     session.commit()
#     session.refresh(pedido)

#     return pedido


# @order_routes.post("/{id_pedido}/cancelar", response_model=ResponseMensagem)
# async def cancelar_pedido(
#     id_pedido: int,
#     session: Session = Depends(pegar_sessao),
#     usuario: Usuario = Depends(verificar_token),
# ):
#     pedido = _pedido_autorizado(id_pedido, session, usuario)
#     _exigir_pendente(pedido)

#     pedido.status = StatusPedido.CANCELADO
#     session.commit()

#     return ResponseMensagem(mensagem=f"Pedido {pedido.id} cancelado")


# @order_routes.post("/{id_pedido}/finalizar", response_model=ResponseMensagem)
# async def finalizar_pedido(
#     id_pedido: int,
#     session: Session = Depends(pegar_sessao),
#     usuario: Usuario = Depends(verificar_token),
# ):
#     pedido = _pedido_autorizado(id_pedido, session, usuario)
#     _exigir_pendente(pedido)

#     if not pedido.itens:
#         raise HTTPException(
#             status_code=status.HTTP_400_BAD_REQUEST,
#             detail="Nao da para finalizar um pedido sem itens",
#         )

#     pedido.status = StatusPedido.FINALIZADO
#     session.commit()

#     return ResponseMensagem(
#         mensagem=f"Pedido {pedido.id} finalizado. Total: R$ {pedido.preco:.2f}"
#     )
