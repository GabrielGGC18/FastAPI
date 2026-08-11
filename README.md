# API de Pedidos — FastAPI

Projeto de estudo: uma API REST de pedidos (tipo pizzaria) com **FastAPI + SQLAlchemy + JWT**.

## Como rodar

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
python -c "import secrets; print(secrets.token_hex(32))"   # cole em SECRET_KEY

uvicorn main:app --reload
```

Docs interativas: <http://127.0.0.1:8000/docs>

## Migrations (Alembic)

O banco nao nasce mais via `Base.metadata.create_all()`. Toda mudanca de schema
vira migration, aplicada explicitamente:

```bash
alembic upgrade head              # aplica migrations pendentes, cria/atualiza banco.db
alembic revision --autogenerate -m "descricao da mudanca"   # gera migration a partir dos models
alembic current                   # mostra em que migration o banco esta
```

`criar_banco()` em `models.py` ficou como referencia comentada em `main.py` —
nao e mais chamado.

## Estrutura

| Arquivo             | Responsabilidade                                              |
| ------------------- | ------------------------------------------------------------- |
| `models.py`         | Tabelas SQLAlchemy: `Usuario`, `Pedido`, `ItemPedido`         |
| `schemas.py`        | Contratos Pydantic de entrada/saida da API                    |
| `settings.py`       | Config via pydantic-settings, le variaveis do `.env`          |
| `security.py`       | Hash de senha (bcrypt) e emissao/leitura de JWT               |
| `dependencies.py`   | `Depends`: sessao de banco, token, admin                      |
| `auth_routes.py`    | `/auth` — cadastro, login, refresh                            |
| `orders_routes.py`  | `/pedidos` — CRUD, itens, cancelar/finalizar                  |
| `main.py`           | Monta o `app` e pluga os routers                              |

A separacao importa: **models descrevem o banco, schemas descrevem a API**. Sao coisas
diferentes de proposito — e por isso que `UsuarioResponse` nao tem o campo `senha`.

## Endpoints

### Auth

| Metodo | Rota                 | O que faz                                       |
| ------ | -------------------- | ----------------------------------------------- |
| POST   | `/auth/criar_conta`  | Cadastra usuario (senha vira hash bcrypt)       |
| POST   | `/auth/login`        | Login via JSON → access + refresh token         |
| POST   | `/auth/login-form`   | Login via form OAuth2 (usado pelo botao do /docs) |
| POST   | `/auth/refresh`      | Troca refresh token por par novo                |
| GET    | `/auth/eu`           | Devolve o dono do token                         |

### Pedidos (todas exigem token)

| Metodo | Rota                       | O que faz                              |
| ------ | -------------------------- | -------------------------------------- |
| POST   | `/pedidos/`                | Cria pedido vazio (PENDENTE, preco 0)  |
| GET    | `/pedidos/`                | Lista pedidos (admin ve todos)         |
| GET    | `/pedidos/{id}`            | Detalhe do pedido                      |
| POST   | `/pedidos/{id}/itens`      | Adiciona item e recalcula o total      |
| DELETE | `/pedidos/itens/{id_item}` | Remove item e recalcula o total        |
| POST   | `/pedidos/{id}/cancelar`   | PENDENTE → CANCELADO                   |
| POST   | `/pedidos/{id}/finalizar`  | PENDENTE → FINALIZADO (exige itens)    |

## Fluxo pra testar no /docs

1. `POST /auth/criar_conta` com `{"nome": "Gabriel", "email": "g@teste.com", "senha": "senha123"}`
2. Clique em **Authorize** (canto superior direito). Use o e-mail no campo `username`.
3. `POST /pedidos/` com `{}` → anote o `id`.
4. `POST /pedidos/{id}/itens` com `{"quantidade": 2, "sabor": "Calabresa", "tamanho": "G", "preco_unitario": 50}`
5. Repare que o `preco` do pedido virou `100.0` sozinho.
6. `POST /pedidos/{id}/finalizar`.

## Testes

```bash
pytest -v
```

## Material de estudo

- [Modelagem de dados](docs/modelagem-de-dados.md) — relacionamentos, chaves, cascade, dado derivado
- [Cheatsheet FastAPI](docs/cheatsheet-fastapi.md) — consulta rapida
- [Exercicios](docs/exercicios.md) — 12 desafios com gabarito

## Decisoes que fogem do curso padrao

- **bcrypt direto, sem `passlib`.** O `passlib` 1.7.4 quebrou com `bcrypt >= 4.1`
  (estoura `ValueError: password cannot be longer than 72 bytes` na deteccao do
  backend). `security.py` chama a lib `bcrypt` direto — mesma primitiva, sem a
  camada abandonada em cima.
- **`status` e um `Enum`, nao uma `String` solta.** O banco passa a rejeitar
  status invalido; antes qualquer texto entrava.
- **`access_token` e `refresh_token` tem escopos separados.** Um access token
  vazado nao consegue gerar tokens novos — ele so expira.
