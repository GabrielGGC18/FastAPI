"""Rotas de pedido: CRUD + itens + transicoes de status.

Regra de autorizacao que se repete aqui: um usuario comum so enxerga e mexe nos
proprios pedidos; um admin mexe em qualquer um. Isso esta centralizado em
`_pedido_autorizado` para nao ficar espalhado por seis rotas.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import select
from dependencies import pegar_sessao, verificar_admin, verificar_token
from models import Cupom, ItemPedido, ItemTemplate, Pedido, PedidoTemplate, StatusPedido, Usuario
from schemas import (
    AplicarCupomSchema,
    ItemPedidoSchema,
    ItemPedidoUpdate,
    PedidoResponse,
    PedidoSchema,
    CupomResponse,
    CupomSchema,
    PedidoTemplateResponse,
    PedidoTemplateSchema,
    ResponseMensagem,
)

from typing import Annotated
from schemas import FilterPage
from sqlalchemy.ext.asyncio import AsyncSession
order_routes = APIRouter(
    prefix="/pedidos",
    tags=["pedidos"],
    # Dependencia no router inteiro: nenhuma rota daqui roda sem token valido.
    dependencies=[Depends(verificar_token)],
)
@order_routes.post("/", response_model=PedidoResponse, status_code=status.HTTP_201_CREATED)
async def criar_pedido(
    pedido_schema: PedidoSchema,
    session: Annotated[AsyncSession, Depends(pegar_sessao)],
    usuario: Annotated[Usuario, Depends(verificar_token)],
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
    await session.commit()
    await session.refresh(novo_pedido)

    return novo_pedido

async def _pedido_autorizado(
    id_pedido: int,
    session:AsyncSession,
    usuario: Usuario,) -> Pedido:
    """Busca o pedido e confere se usuário pode tocá-lo."""
    pedido = await session.scalar(select(Pedido).where(Pedido.id == id_pedido))
    
    if not pedido:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail = "Pedido não encontrado",
        )
    if not usuario.admin and pedido.usuario_id != usuario.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail = "Você não tem permissão sobre este pedido",
        )
    return pedido
async def _recalcular_preco(pedido: Pedido, session: AsyncSession) -> float:
    """Recalcula preco do pedido aplicando o desconto do cupom, se houver."""
    percentual = 0.0
    if pedido.cupom_codigo:
        cupom = await session.scalar(select(Cupom).where(Cupom.codigo == pedido.cupom_codigo))
        if cupom and cupom.ativo:
            percentual = cupom.percentual_desconto
    return pedido.calcular_preco(percentual)


def _exigir_pendente(pedido: Pedido) -> None:
    """Pedido Cancelado, finalizado ou Imutável."""
    if pedido.status != StatusPedido.PENDENTE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail = f"Pedido {pedido.status.value} não pode mais ser alterado",
        )
@order_routes.get("/{id_pedido}",  response_model=PedidoResponse)
async def visualizar_pedido(
    id_pedido: int,
    session: Annotated[AsyncSession, Depends(pegar_sessao)],
    usuario: Annotated[Usuario, Depends(verificar_token)],   
):
    return await _pedido_autorizado(id_pedido, session, usuario)
@order_routes.get("/", response_model=list[PedidoResponse])
async def listar_pedidos(
    filtros: Annotated[FilterPage, Depends()],
    session: Annotated[AsyncSession, Depends(pegar_sessao)],
    usuario: Annotated[Usuario, Depends(verificar_token)],
):
    """Admin vê tudo; usuário comum vê só os pedidos dele."""
    query = select(Pedido)
    
    if not usuario.admin:
        query = query.where(Pedido.usuario_id == usuario.id)
    resultado = await session.scalars(query.offset(filtros.offset).limit(filtros.limit))    
    return resultado.all()


@order_routes.post("/{id_pedido}/itens", response_model=PedidoResponse)
async def adicionar_item(
    id_pedido: int,
    item_schema: ItemPedidoSchema,
    session: Annotated[AsyncSession, Depends(pegar_sessao)],
    usuario: Annotated[Usuario, Depends(verificar_token)],
):
    """Adiciona item e recalcula o total do pedido."""
    pedido = await _pedido_autorizado(id_pedido, session, usuario)
    _exigir_pendente(pedido)
    
    item = ItemPedido(
        quantidade=item_schema.quantidade,
        sabor=item_schema.sabor,
        tamanho=item_schema.tamanho,
        preco_unitario=item_schema.preco_unitario,
        pedido_id=pedido.id,
        observacao=item_schema.observacao,
    )

    session.add(item)
    await session.flush() #Empurra o INSERT para o banco sem fechar a transacao, assim `pedido.itens` ja enxerga o item novo.
    await session.refresh(pedido)
    await _recalcular_preco(pedido, session)
    await session.commit()
    await session.refresh(pedido)
    return pedido 

@order_routes.delete("/itens/{id_item}", response_model=PedidoResponse)
async def remover_item(
    id_item: int,
    session: Annotated[AsyncSession, Depends(pegar_sessao)],
    usuario: Annotated[Usuario, Depends(verificar_token)]
):
    item = await session.scalar(select(ItemPedido).where(ItemPedido.id == id_item))
    if not item:
        raise  HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item não encontrado",
        )

    pedido = await _pedido_autorizado(item.pedido_id, session, usuario)
    _exigir_pendente(pedido)

    await session.delete(item)
    await session.flush()
    await session.refresh(pedido)

    await _recalcular_preco(pedido, session)
    await session.commit()
    await session.refresh(pedido)

    return pedido

@order_routes.post("/{id_pedido}/cancelar", response_model=ResponseMensagem)
async def cancelar_pedido(
    id_pedido: int,
    session: Annotated[AsyncSession, Depends(pegar_sessao)],
    usuario: Annotated[Usuario, Depends(verificar_token)],
):

    pedido = await _pedido_autorizado(id_pedido, session, usuario)
    _exigir_pendente(pedido)
    
    pedido.status = StatusPedido.CANCELADO
    await session.commit()
    await session.refresh(pedido)

    return ResponseMensagem(mensagem=f"Pedido {pedido.id} cancelado")

@order_routes.post("/{id_pedido}/finalizar", response_model=ResponseMensagem)
async def finalizar_pedido(
    id_pedido: int,
    session: Annotated[AsyncSession, Depends(pegar_sessao)],
    usuario: Annotated[Usuario, Depends(verificar_token)],
):
    pedido = await _pedido_autorizado(id_pedido, session, usuario)
    _exigir_pendente(pedido)
    
    if not pedido.itens:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Não da para finalizar um pedido sem itens",
        )
    pedido.status = StatusPedido.FINALIZADO
    await session.commit()
    await session.refresh(pedido)

    return ResponseMensagem(
        mensagem=f"Pedido {pedido.id} finalizado. Total: R$ {pedido.preco:.2f}"
    )
@order_routes.patch("/itens/{id_item}", response_model=PedidoResponse)
async def atualizar_item(
    id_item: int,
    item_update: ItemPedidoUpdate,
    session: Annotated[AsyncSession, Depends(pegar_sessao)],
    usuario: Annotated[Usuario, Depends(verificar_token)],
):
    item = await session.scalar(select(ItemPedido).where(ItemPedido.id == id_item))
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Item não encontrado",
        )

    pedido = await _pedido_autorizado(item.pedido_id, session, usuario)
    _exigir_pendente(pedido)

    # Atualiza apenas os campos fornecidos
    for field, value in item_update.model_dump(exclude_unset=True).items():
        setattr(item, field, value)

    await session.flush()
    await session.refresh(pedido)

    await _recalcular_preco(pedido, session)
    await session.commit()
    await session.refresh(pedido)

    return pedido

# ------------------------------------------------------------------ cupom


@order_routes.post("/cupons", response_model=CupomResponse, status_code=status.HTTP_201_CREATED)
async def criar_cupom(
    
    dados: CupomSchema,
    session: Annotated[AsyncSession, Depends(pegar_sessao)],
    usuario: Annotated[Usuario, Depends(verificar_admin)],
):
    """So admin cria cupom."""
    existente = await session.scalar(select(Cupom).where(Cupom.codigo == dados.codigo))
    if existente:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cupom ja existe")

    cupom = Cupom(codigo=dados.codigo, percentual_desconto=dados.percentual_desconto)
    session.add(cupom)
    await session.commit()
    await session.refresh(cupom)
    return cupom


@order_routes.post("/{id_pedido}/aplicar-cupom", response_model=PedidoResponse)
async def aplicar_cupom(
    id_pedido: int,
    dados: AplicarCupomSchema,
    session: Annotated[AsyncSession, Depends(pegar_sessao)],
    usuario: Annotated[Usuario, Depends(verificar_token)],
):
    pedido = await _pedido_autorizado(id_pedido, session, usuario)
    _exigir_pendente(pedido)

    cupom = await session.scalar(select(Cupom).where(Cupom.codigo == dados.codigo))
    if not cupom or not cupom.ativo:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Cupom invalido ou inativo",
        )

    pedido.cupom_codigo = cupom.codigo
    await _recalcular_preco(pedido, session)
    await session.commit()
    await session.refresh(pedido)

    return pedido


@order_routes.delete("/{id_pedido}/cupom", response_model=PedidoResponse)
async def remover_cupom(
    id_pedido: int,
    session: Annotated[AsyncSession, Depends(pegar_sessao)],
    usuario: Annotated[Usuario, Depends(verificar_token)],
):
    """Desfaz o cupom aplicado, recalcula preco sem desconto."""
    pedido = await _pedido_autorizado(id_pedido, session, usuario)
    _exigir_pendente(pedido)

    if not pedido.cupom_codigo:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Pedido não tem cupom aplicado",
        )

    pedido.cupom_codigo = None
    await _recalcular_preco(pedido, session)
    await session.commit()
    await session.refresh(pedido)

    return pedido


# --------------------------------------------------------------- duplicar


@order_routes.post("/{id_pedido}/duplicar", response_model=PedidoResponse, status_code=status.HTTP_201_CREATED)
async def duplicar_pedido(
    id_pedido: int,
    session: Annotated[AsyncSession, Depends(pegar_sessao)],
    usuario: Annotated[Usuario, Depends(verificar_token)],
):
    """Clona um pedido antigo (itens inclusos) num pedido PENDENTE novo."""
    pedido_original = await _pedido_autorizado(id_pedido, session, usuario)

    novo_pedido = Pedido(usuario_id=pedido_original.usuario_id)
    session.add(novo_pedido)
    await session.flush()

    for item in pedido_original.itens:
        session.add(
            ItemPedido(
                quantidade=item.quantidade,
                sabor=item.sabor,
                tamanho=item.tamanho,
                preco_unitario=item.preco_unitario,
                pedido_id=novo_pedido.id,
                observacao=item.observacao,
            )
        )

    await session.flush()
    await session.refresh(novo_pedido)
    novo_pedido.calcular_preco()
    await session.commit()
    await session.refresh(novo_pedido)

    return novo_pedido


# --------------------------------------------------------------- templates


@order_routes.post("/templates", response_model=PedidoTemplateResponse, status_code=status.HTTP_201_CREATED)
async def criar_template(
    dados: PedidoTemplateSchema,
    session: Annotated[AsyncSession, Depends(pegar_sessao)],
    usuario: Annotated[Usuario, Depends(verificar_token)],
):
    template = PedidoTemplate(nome=dados.nome, usuario_id=usuario.id)
    session.add(template)
    await session.flush()

    for item in dados.itens:
        session.add(
            ItemTemplate(
                quantidade=item.quantidade,
                sabor=item.sabor,
                tamanho=item.tamanho,
                preco_unitario=item.preco_unitario,
                template_id=template.id,
            )
        )

    await session.commit()
    await session.refresh(template)
    return template


@order_routes.get("/templates", response_model=list[PedidoTemplateResponse])
async def listar_templates(
    session: Annotated[AsyncSession, Depends(pegar_sessao)],
    usuario: Annotated[Usuario, Depends(verificar_token)],
):
    resultado = await session.scalars(
        select(PedidoTemplate).where(PedidoTemplate.usuario_id == usuario.id)
    )
    return resultado.all()


async def _template_autorizado(id_template: int, session: AsyncSession, usuario: Usuario) -> PedidoTemplate:
    template = await session.scalar(select(PedidoTemplate).where(PedidoTemplate.id == id_template))
    if not template:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template não encontrado")
    if not usuario.admin and template.usuario_id != usuario.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Você não tem permissão sobre este template")
    return template


@order_routes.delete("/templates/{id_template}", response_model=ResponseMensagem)
async def remover_template(
    id_template: int,
    session: Annotated[AsyncSession, Depends(pegar_sessao)],
    usuario: Annotated[Usuario, Depends(verificar_token)],
):
    template = await _template_autorizado(id_template, session, usuario)
    await session.delete(template)
    await session.commit()
    return ResponseMensagem(mensagem=f"Template {id_template} removido")


@order_routes.post("/templates/{id_template}/usar", response_model=PedidoResponse, status_code=status.HTTP_201_CREATED)
async def usar_template(
    id_template: int,
    session: Annotated[AsyncSession, Depends(pegar_sessao)],
    usuario: Annotated[Usuario, Depends(verificar_token)],
):
    """Cria um pedido PENDENTE novo a partir dos itens do template."""
    template = await _template_autorizado(id_template, session, usuario)

    novo_pedido = Pedido(usuario_id=usuario.id)
    session.add(novo_pedido)
    await session.flush()

    for item in template.itens:
        session.add(
            ItemPedido(
                quantidade=item.quantidade,
                sabor=item.sabor,
                tamanho=item.tamanho,
                preco_unitario=item.preco_unitario,
                pedido_id=novo_pedido.id,
            )
        )

    await session.flush()
    await session.refresh(novo_pedido)
    novo_pedido.calcular_preco()
    await session.commit()
    await session.refresh(novo_pedido)

    return novo_pedido
