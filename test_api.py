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

@pytest.mark.asyncio
async def test_atualizar_item_altera_so_campos_enviados(client):
    headers = await criar_e_logar(client)
    resposta = await client.post("/pedidos/", json={}, headers=headers)
    pedido = resposta.json()

    resposta = await client.post(
        f"/pedidos/{pedido['id']}/itens",
        json={"quantidade": 2, "sabor": "Calabresa", "tamanho": "M", "preco_unitario": 40.0},
        headers=headers,
    )
    id_item = resposta.json()["itens"][0]["id"]

    resposta = await client.patch(
        f"/pedidos/itens/{id_item}", json={"quantidade": 3}, headers=headers
    )
    assert resposta.status_code == 200
    item = resposta.json()["itens"][0]
    assert item["quantidade"] == 3
    assert item["sabor"] == "Calabresa"  # nao enviado, permanece igual
    assert resposta.json()["preco"] == 120.0  # 3 * 40.0, recalculado


@pytest.mark.asyncio
async def test_atualizar_item_de_outro_usuario_da_403(client):
    dono = await criar_e_logar(client, email="dono@teste.com")
    resposta = await client.post("/pedidos/", json={}, headers=dono)
    pedido = resposta.json()
    resposta = await client.post(
        f"/pedidos/{pedido['id']}/itens",
        json={"quantidade": 1, "sabor": "X", "tamanho": "P", "preco_unitario": 10.0},
        headers=dono,
    )
    id_item = resposta.json()["itens"][0]["id"]

    intruso = await criar_e_logar(client, email="intruso@teste.com")
    resposta = await client.patch(
        f"/pedidos/itens/{id_item}", json={"quantidade": 5}, headers=intruso
    )
    assert resposta.status_code == 403


@pytest.mark.asyncio
async def test_item_com_observacao(client):
    headers = await criar_e_logar(client)
    pedido = (await client.post("/pedidos/", json={}, headers=headers)).json()
    resposta = await client.post(
        f"/pedidos/{pedido['id']}/itens",
        json={
            "quantidade": 1,
            "sabor": "X",
            "tamanho": "M",
            "preco_unitario": 30.0,
            "observacao": "sem cebola",
        },
        headers=headers,
    )
    assert resposta.json()["itens"][0]["observacao"] == "sem cebola"


@pytest.mark.asyncio
async def test_duplicar_pedido_clona_itens(client):
    headers = await criar_e_logar(client)
    pedido = (await client.post("/pedidos/", json={}, headers=headers)).json()
    await client.post(
        f"/pedidos/{pedido['id']}/itens",
        json={"quantidade": 2, "sabor": "X", "tamanho": "M", "preco_unitario": 20.0},
        headers=headers,
    )
    resposta = await client.post(f"/pedidos/{pedido['id']}/duplicar", headers=headers)
    assert resposta.status_code == 201
    novo = resposta.json()
    assert novo["id"] != pedido["id"]
    assert novo["status"] == "PENDENTE"
    assert len(novo["itens"]) == 1
    assert novo["preco"] == 40.0


@pytest.mark.asyncio
async def test_duplicar_pedido_de_outro_da_403(client):
    dono = await criar_e_logar(client, email="dono@teste.com")
    pedido = (await client.post("/pedidos/", json={}, headers=dono)).json()
    intruso = await criar_e_logar(client, email="intruso@teste.com")
    resposta = await client.post(f"/pedidos/{pedido['id']}/duplicar", headers=intruso)
    assert resposta.status_code == 403


@pytest.mark.asyncio
async def test_cupom_aplica_desconto(client):
    admin = await criar_e_logar(client, email="admin@teste.com", admin=True)
    await client.post(
        "/pedidos/cupons", json={"codigo": "PROMO10", "percentual_desconto": 10}, headers=admin
    )

    headers = await criar_e_logar(client, email="cliente@teste.com")
    pedido = (await client.post("/pedidos/", json={}, headers=headers)).json()
    await client.post(
        f"/pedidos/{pedido['id']}/itens",
        json={"quantidade": 1, "sabor": "X", "tamanho": "M", "preco_unitario": 100.0},
        headers=headers,
    )
    resposta = await client.post(
        f"/pedidos/{pedido['id']}/aplicar-cupom", json={"codigo": "PROMO10"}, headers=headers
    )
    assert resposta.status_code == 200
    assert resposta.json()["preco"] == 90.0


@pytest.mark.asyncio
async def test_cupom_invalido_da_404(client):
    headers = await criar_e_logar(client)
    pedido = (await client.post("/pedidos/", json={}, headers=headers)).json()
    resposta = await client.post(
        f"/pedidos/{pedido['id']}/aplicar-cupom", json={"codigo": "NAOEXISTE"}, headers=headers
    )
    assert resposta.status_code == 404


@pytest.mark.asyncio
async def test_criar_cupom_exige_admin(client):
    headers = await criar_e_logar(client)
    resposta = await client.post(
        "/pedidos/cupons", json={"codigo": "X", "percentual_desconto": 5}, headers=headers
    )
    assert resposta.status_code == 403


@pytest.mark.asyncio
async def test_template_criar_e_usar(client):
    headers = await criar_e_logar(client)
    resposta = await client.post(
        "/pedidos/templates",
        json={
            "nome": "Combo favorito",
            "itens": [
                {"quantidade": 1, "sabor": "Calabresa", "tamanho": "G", "preco_unitario": 45.0}
            ],
        },
        headers=headers,
    )
    assert resposta.status_code == 201
    template = resposta.json()

    listagem = await client.get("/pedidos/templates", headers=headers)
    assert len(listagem.json()) == 1

    resposta = await client.post(f"/pedidos/templates/{template['id']}/usar", headers=headers)
    assert resposta.status_code == 201
    pedido = resposta.json()
    assert pedido["status"] == "PENDENTE"
    assert len(pedido["itens"]) == 1
    assert pedido["preco"] == 45.0


@pytest.mark.asyncio
async def test_template_de_outro_usuario_da_403(client):
    dono = await criar_e_logar(client, email="dono@teste.com")
    template = (
        await client.post(
            "/pedidos/templates",
            json={"nome": "T", "itens": [{"quantidade": 1, "sabor": "X", "tamanho": "P", "preco_unitario": 10.0}]},
            headers=dono,
        )
    ).json()

    intruso = await criar_e_logar(client, email="intruso@teste.com")
    resposta = await client.post(f"/pedidos/templates/{template['id']}/usar", headers=intruso)
    assert resposta.status_code == 403


@pytest.mark.asyncio
async def test_cancelar_pedido(client):
    headers = await criar_e_logar(client)
    pedido = (await client.post("/pedidos/", json={}, headers=headers)).json()

    resposta = await client.post(f"/pedidos/{pedido['id']}/cancelar", headers=headers)
    assert resposta.status_code == 200
    assert "cancelado" in resposta.json()["mensagem"]

    verificacao = await client.get(f"/pedidos/{pedido['id']}", headers=headers)
    assert verificacao.json()["status"] == "CANCELADO"


@pytest.mark.asyncio
async def test_cancelar_pedido_ja_cancelado_da_400(client):
    headers = await criar_e_logar(client)
    pedido = (await client.post("/pedidos/", json={}, headers=headers)).json()
    await client.post(f"/pedidos/{pedido['id']}/cancelar", headers=headers)

    resposta = await client.post(f"/pedidos/{pedido['id']}/cancelar", headers=headers)
    assert resposta.status_code == 400


@pytest.mark.asyncio
async def test_cancelar_pedido_de_outro_da_403(client):
    dono = await criar_e_logar(client, email="dono@teste.com")
    pedido = (await client.post("/pedidos/", json={}, headers=dono)).json()

    intruso = await criar_e_logar(client, email="intruso@teste.com")
    resposta = await client.post(f"/pedidos/{pedido['id']}/cancelar", headers=intruso)
    assert resposta.status_code == 403


@pytest.mark.asyncio
async def test_remover_cupom_volta_preco_cheio(client):
    admin = await criar_e_logar(client, email="admin@teste.com", admin=True)
    await client.post(
        "/pedidos/cupons", json={"codigo": "PROMO20", "percentual_desconto": 20}, headers=admin
    )

    headers = await criar_e_logar(client, email="cliente@teste.com")
    pedido = (await client.post("/pedidos/", json={}, headers=headers)).json()
    await client.post(
        f"/pedidos/{pedido['id']}/itens",
        json={"quantidade": 1, "sabor": "X", "tamanho": "M", "preco_unitario": 100.0},
        headers=headers,
    )
    await client.post(
        f"/pedidos/{pedido['id']}/aplicar-cupom", json={"codigo": "PROMO20"}, headers=headers
    )

    resposta = await client.delete(f"/pedidos/{pedido['id']}/cupom", headers=headers)
    assert resposta.status_code == 200
    assert resposta.json()["preco"] == 100.0
    assert resposta.json()["cupom_codigo"] is None


@pytest.mark.asyncio
async def test_remover_cupom_sem_cupom_aplicado_da_400(client):
    headers = await criar_e_logar(client)
    pedido = (await client.post("/pedidos/", json={}, headers=headers)).json()

    resposta = await client.delete(f"/pedidos/{pedido['id']}/cupom", headers=headers)
    assert resposta.status_code == 400


async def test_token_expirado_da_401(client):
    with freeze_time("2026-01-01 12:00:00"):
        headers = await criar_e_logar(client)
    with freeze_time("2026-01-01 12:31:00"):
        resposta = await client.get("/auth/eu", headers=headers)
    assert resposta.status_code == 401
        