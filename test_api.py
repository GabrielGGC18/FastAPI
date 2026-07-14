"""Testes da API.

Rodar: pytest -v

Cada teste roda contra um banco SQLite em memoria, criado do zero. Nao encosta
no `banco.db` de desenvolvimento.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from dependencies import pegar_sessao
from main import app
from models import Base


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        # Sem StaticPool, cada conexao abre um banco :memory: NOVO e vazio:
        # criamos as tabelas numa conexao e a rota abriria outra, sem tabela.
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def pegar_sessao_teste():
        session = TestSession()
        try:
            yield session
        finally:
            session.close()

    # E isto que torna a rota testavel: como a sessao entra por `Depends`,
    # da para trocar ela aqui sem mexer no codigo de producao.
    app.dependency_overrides[pegar_sessao] = pegar_sessao_teste
    yield TestClient(app)
    app.dependency_overrides.clear()


def criar_e_logar(client, email="g@teste.com", senha="senha123", admin=False):
    """Helper: cadastra, loga e devolve o header de Authorization."""
    client.post(
        "/auth/criar_conta",
        json={"nome": "Teste", "email": email, "senha": senha, "admin": admin},
    )
    resposta = client.post("/auth/login", json={"email": email, "senha": senha})
    token = resposta.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ----------------------------------------------------------------- auth


def test_criar_conta_nao_devolve_senha(client):
    resposta = client.post(
        "/auth/criar_conta",
        json={"nome": "Gabriel", "email": "g@teste.com", "senha": "senha123"},
    )
    assert resposta.status_code == 201
    assert "senha" not in resposta.json()


def test_email_duplicado_da_400(client):
    dados = {"nome": "Gabriel", "email": "g@teste.com", "senha": "senha123"}
    client.post("/auth/criar_conta", json=dados)

    resposta = client.post("/auth/criar_conta", json=dados)
    assert resposta.status_code == 400


def test_senha_curta_da_422(client):
    resposta = client.post(
        "/auth/criar_conta",
        json={"nome": "Gabriel", "email": "g@teste.com", "senha": "123"},
    )
    assert resposta.status_code == 422


def test_login_com_senha_errada_da_401(client):
    criar_e_logar(client)

    resposta = client.post(
        "/auth/login", json={"email": "g@teste.com", "senha": "errada"}
    )
    assert resposta.status_code == 401


def test_access_token_nao_serve_para_refresh(client):
    """Escopos separados: o access token nao pode gerar tokens novos."""
    headers = criar_e_logar(client)

    assert client.post("/auth/refresh", headers=headers).status_code == 401


def test_refresh_token_gera_par_novo(client):
    client.post(
        "/auth/criar_conta",
        json={"nome": "Gabriel", "email": "g@teste.com", "senha": "senha123"},
    )
    login = client.post(
        "/auth/login", json={"email": "g@teste.com", "senha": "senha123"}
    )
    refresh = login.json()["refresh_token"]

    resposta = client.post(
        "/auth/refresh", headers={"Authorization": f"Bearer {refresh}"}
    )
    assert resposta.status_code == 200
    assert "access_token" in resposta.json()


# --------------------------------------------------------------- pedidos


def test_pedidos_exige_token(client):
    assert client.get("/pedidos/").status_code == 401


def test_preco_e_recalculado_ao_adicionar_item(client):
    headers = criar_e_logar(client)
    pedido = client.post("/pedidos/", json={}, headers=headers).json()
    assert pedido["preco"] == 0.0

    resposta = client.post(
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


def test_preco_e_recalculado_ao_remover_item(client):
    headers = criar_e_logar(client)
    pedido = client.post("/pedidos/", json={}, headers=headers).json()

    for preco in (50.0, 30.0):
        resposta = client.post(
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
    resposta = client.delete(f"/pedidos/itens/{id_item}", headers=headers)
    assert resposta.json()["preco"] == 50.0


def test_quantidade_zero_da_422(client):
    headers = criar_e_logar(client)
    pedido = client.post("/pedidos/", json={}, headers=headers).json()

    resposta = client.post(
        f"/pedidos/{pedido['id']}/itens",
        json={"quantidade": 0, "sabor": "X", "tamanho": "P", "preco_unitario": 10.0},
        headers=headers,
    )
    assert resposta.status_code == 422


def test_nao_finaliza_pedido_sem_itens(client):
    headers = criar_e_logar(client)
    pedido = client.post("/pedidos/", json={}, headers=headers).json()

    resposta = client.post(f"/pedidos/{pedido['id']}/finalizar", headers=headers)
    assert resposta.status_code == 400


def test_pedido_finalizado_e_imutavel(client):
    headers = criar_e_logar(client)
    pedido = client.post("/pedidos/", json={}, headers=headers).json()
    client.post(
        f"/pedidos/{pedido['id']}/itens",
        json={"quantidade": 1, "sabor": "X", "tamanho": "M", "preco_unitario": 50.0},
        headers=headers,
    )
    client.post(f"/pedidos/{pedido['id']}/finalizar", headers=headers)

    adicionar = client.post(
        f"/pedidos/{pedido['id']}/itens",
        json={"quantidade": 1, "sabor": "Y", "tamanho": "P", "preco_unitario": 10.0},
        headers=headers,
    )
    cancelar = client.post(f"/pedidos/{pedido['id']}/cancelar", headers=headers)

    assert adicionar.status_code == 400
    assert cancelar.status_code == 400


# --------------------------------------------------------- autorizacao


def test_usuario_nao_ve_pedido_alheio(client):
    dono = criar_e_logar(client, email="dono@teste.com")
    pedido = client.post("/pedidos/", json={}, headers=dono).json()

    intruso = criar_e_logar(client, email="intruso@teste.com")
    resposta = client.get(f"/pedidos/{pedido['id']}", headers=intruso)

    assert resposta.status_code == 403


def test_listagem_so_traz_pedidos_do_usuario(client):
    dono = criar_e_logar(client, email="dono@teste.com")
    client.post("/pedidos/", json={}, headers=dono)

    intruso = criar_e_logar(client, email="intruso@teste.com")
    assert client.get("/pedidos/", headers=intruso).json() == []


def test_admin_ve_pedido_dos_outros(client):
    dono = criar_e_logar(client, email="dono@teste.com")
    pedido = client.post("/pedidos/", json={}, headers=dono).json()

    admin = criar_e_logar(client, email="admin@teste.com", admin=True)
    resposta = client.get(f"/pedidos/{pedido['id']}", headers=admin)

    assert resposta.status_code == 200
    assert len(client.get("/pedidos/", headers=admin).json()) == 1


def test_usuario_comum_nao_cria_pedido_para_outro(client):
    dono = criar_e_logar(client, email="dono@teste.com")
    intruso = criar_e_logar(client, email="intruso@teste.com")

    resposta = client.post("/pedidos/", json={"usuario_id": 1}, headers=intruso)
    assert resposta.status_code == 403
