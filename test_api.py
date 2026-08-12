"""Testes da API.

Rodar: pytest -v

Cada teste roda contra um banco SQLite em memoria, criado do zero. Nao encosta
no `banco.db` de desenvolvimento.
"""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import StaticPool

from dependencies import pegar_sessao
from main import app
from models import Base

import factory
from freezegun import freeze_time
class UsuarioFactory(factory.Factory):
    class Meta:
        model = dict #Gera um dicionário simples em vez de um objeto ORM(sqlalchemy) - Vamos usar só para montar o payload do POST

    nome = factory.Sequence(lambda n : f"usuario{n}")
    email = factory.Sequence(lambda n: f"usuario{n}@teste.com")
    senha = "senha123"
    admin = False
@pytest_asyncio.fixture
async def client():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        # Sem StaticPool, cada conexao abre um banco :memory: NOVO e vazio:
        # criamos as tabelas numa conexao e a rota abriria outra, sem tabela.
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async def pegar_sessao_teste():
        async with AsyncSession(engine) as session:
            yield session

    # E isto que torna a rota testavel: como a sessao entra por `Depends`,
    # da para trocar ela aqui sem mexer no codigo de producao.
    app.dependency_overrides[pegar_sessao] = pegar_sessao_teste
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
    await engine.dispose()


async def criar_e_logar(client, email="g@teste.com", senha="senha123", admin=False):
    """Helper: cadastra, loga e devolve o header de Authorization."""
    await client.post(
        "/auth/criar_conta",
        json={"nome": "Teste", "email": email, "senha": senha, "admin": admin},
    )
    resposta = await client.post("/auth/login", json={"email": email, "senha": senha})
    token = resposta.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ----------------------------------------------------------------- auth


@pytest.mark.asyncio
async def test_criar_conta_nao_devolve_senha(client):
    resposta = await client.post(
        "/auth/criar_conta",
        json={"nome": "Gabriel", "email": "g@teste.com", "senha": "senha123"},
    )
    assert resposta.status_code == 201
    assert "senha" not in resposta.json()


@pytest.mark.asyncio
async def test_email_duplicado_da_400(client):
    dados = {"nome": "Gabriel", "email": "g@teste.com", "senha": "senha123"}
    await client.post("/auth/criar_conta", json=dados)

    resposta = await client.post("/auth/criar_conta", json=dados)
    assert resposta.status_code == 400


@pytest.mark.asyncio
async def test_senha_curta_da_422(client):
    resposta = await client.post(
        "/auth/criar_conta",
        json={"nome": "Gabriel", "email": "g@teste.com", "senha": "123"},
    )
    assert resposta.status_code == 422


@pytest.mark.asyncio
async def test_login_com_senha_errada_da_401(client):
    await criar_e_logar(client)

    resposta = await client.post(
        "/auth/login", json={"email": "g@teste.com", "senha": "errada"}
    )
    assert resposta.status_code == 401


@pytest.mark.asyncio
async def test_access_token_nao_serve_para_refresh(client):
    """Escopos separados: o access token nao pode gerar tokens novos."""
    headers = await criar_e_logar(client)

    resposta = await client.post("/auth/refresh", headers=headers)
    assert resposta.status_code == 401


@pytest.mark.asyncio
async def test_refresh_token_gera_par_novo(client):
    await client.post(
        "/auth/criar_conta",
        json={"nome": "Gabriel", "email": "g@teste.com", "senha": "senha123"},
    )
    login = await client.post(
        "/auth/login", json={"email": "g@teste.com", "senha": "senha123"}
    )
    refresh = login.json()["refresh_token"]

    resposta = await client.post(
        "/auth/refresh", headers={"Authorization": f"Bearer {refresh}"}
    )
    assert resposta.status_code == 200
    assert "access_token" in resposta.json()


# --------------------------------------------------------------- pedidos


@pytest.mark.asyncio
async def test_pedidos_exige_token(client):
    resposta = await client.get("/pedidos/")
    assert resposta.status_code == 401


@pytest.mark.asyncio
async def test_preco_e_recalculado_ao_adicionar_item(client):
    headers = await criar_e_logar(client)
    resposta = await client.post("/pedidos/", json={}, headers=headers)
    pedido = resposta.json()
    assert pedido["preco"] == 0.0

    resposta = await client.post(
        f"/pedidos/{pedido['id']}/itens",
        json={
            "quantidade": 2,
            "sabor": "Calabresa",
            "tamanho": "G",
            "preco_unitario": 50.0,
        },
        headers=headers,
    )
    assert resposta.status_code == 200
    assert resposta.json()["preco"] == 100.0


@pytest.mark.asyncio
async def test_preco_e_recalculado_ao_remover_item(client):
    headers = await criar_e_logar(client)
    resposta = await client.post("/pedidos/", json={}, headers=headers)
    pedido = resposta.json()

    for preco in (50.0, 30.0):
        resposta = await client.post(
            f"/pedidos/{pedido['id']}/itens",
            json={
                "quantidade": 1,
                "sabor": "X",
                "tamanho": "M",
                "preco_unitario": preco,
            },
            headers=headers,
        )
    assert resposta.json()["preco"] == 80.0

    id_item = resposta.json()["itens"][-1]["id"]
    resposta = await client.delete(f"/pedidos/itens/{id_item}", headers=headers)
    assert resposta.json()["preco"] == 50.0


@pytest.mark.asyncio
async def test_quantidade_zero_da_422(client):
    headers = await criar_e_logar(client)
    resposta = await client.post("/pedidos/", json={}, headers=headers)
    pedido = resposta.json()

    resposta = await client.post(
        f"/pedidos/{pedido['id']}/itens",
        json={"quantidade": 0, "sabor": "X", "tamanho": "P", "preco_unitario": 10.0},
        headers=headers,
    )
    assert resposta.status_code == 422


@pytest.mark.asyncio
async def test_nao_finaliza_pedido_sem_itens(client):
    headers = await criar_e_logar(client)
    resposta = await client.post("/pedidos/", json={}, headers=headers)
    pedido = resposta.json()

    resposta = await client.post(f"/pedidos/{pedido['id']}/finalizar", headers=headers)
    assert resposta.status_code == 400


@pytest.mark.asyncio
async def test_pedido_finalizado_e_imutavel(client):
    headers = await criar_e_logar(client)
    resposta = await client.post("/pedidos/", json={}, headers=headers)
    pedido = resposta.json()
    await client.post(
        f"/pedidos/{pedido['id']}/itens",
        json={"quantidade": 1, "sabor": "X", "tamanho": "M", "preco_unitario": 50.0},
        headers=headers,
    )
    await client.post(f"/pedidos/{pedido['id']}/finalizar", headers=headers)

    adicionar = await client.post(
        f"/pedidos/{pedido['id']}/itens",
        json={"quantidade": 1, "sabor": "Y", "tamanho": "P", "preco_unitario": 10.0},
        headers=headers,
    )
    cancelar = await client.post(f"/pedidos/{pedido['id']}/cancelar", headers=headers)

    assert adicionar.status_code == 400
    assert cancelar.status_code == 400


# --------------------------------------------------------- autorizacao


@pytest.mark.asyncio
async def test_usuario_nao_ve_pedido_alheio(client):
    dono = await criar_e_logar(client, email="dono@teste.com")
    resposta = await client.post("/pedidos/", json={}, headers=dono)
    pedido = resposta.json()

    intruso = await criar_e_logar(client, email="intruso@teste.com")
    resposta = await client.get(f"/pedidos/{pedido['id']}", headers=intruso)

    assert resposta.status_code == 403


@pytest.mark.asyncio
async def test_listagem_so_traz_pedidos_do_usuario(client):
    dono = await criar_e_logar(client, email="dono@teste.com")
    await client.post("/pedidos/", json={}, headers=dono)

    intruso = await criar_e_logar(client, email="intruso@teste.com")
    resposta = await client.get("/pedidos/", headers=intruso)
    assert resposta.json() == []


@pytest.mark.asyncio
async def test_admin_ve_pedido_dos_outros(client):
    dono = await criar_e_logar(client, email="dono@teste.com")
    resposta = await client.post("/pedidos/", json={}, headers=dono)
    pedido = resposta.json()

    admin = await criar_e_logar(client, email="admin@teste.com", admin=True)
    resposta = await client.get(f"/pedidos/{pedido['id']}", headers=admin)

    assert resposta.status_code == 200

    resposta = await client.get("/pedidos/", headers=admin)
    assert len(resposta.json()) == 1


@pytest.mark.asyncio
async def test_usuario_comum_nao_cria_pedido_para_outro(client):
    await criar_e_logar(client, email="dono@teste.com")
    intruso = await criar_e_logar(client, email="intruso@teste.com")

    resposta = await client.post("/pedidos/", json={"usuario_id": 1}, headers=intruso)
    assert resposta.status_code == 403

async def test_token_expirado_da_401(client):
    with freeze_time("2026-01-01 12:00:00"):
        headers = await criar_e_logar(client)
    with freeze_time("2026-01-01 12:31:00"):
        resposta = await client.get("/auth/eu", headers=headers)
    assert resposta.status_code == 401
        