# Cheatsheet FastAPI

Consulta rapida. Tudo aqui aparece em algum arquivo do projeto — o ponteiro esta na margem.

---

## Rotas e parametros

```python
from fastapi import APIRouter, Query

router = APIRouter(prefix="/pedidos", tags=["pedidos"])

@router.get("/{id_pedido}")                 # path param: vem da URL
async def ver(id_pedido: int): ...

@router.get("/")                            # query param: ?limite=10
async def listar(limite: int = Query(10, le=100)): ...

@router.post("/")                           # body: vem do JSON, tipado com Pydantic
async def criar(dados: PedidoSchema): ...
```

**Como o FastAPI decide o que e o que:** se o nome do parametro esta no path → path param.
Se o tipo e um `BaseModel` → body. Qualquer outra coisa → query param. Nao tem
configuracao, e so isso.

⚠️ **Ordem das rotas importa.** `/pedidos/{id}` declarada antes de `/pedidos/itens` faz o
FastAPI tentar casar `"itens"` como `id: int` e devolver `422`. **Rota literal sempre antes
de rota com parametro.**

---

## Status codes

```python
from fastapi import status

@router.post("/", status_code=status.HTTP_201_CREATED)   # default e 200
```

| Codigo | Quando usar                                             |
| ------ | ------------------------------------------------------- |
| `200`  | OK (GET, ou POST que nao criou recurso)                 |
| `201`  | Criou recurso (`POST /auth/criar_conta`)                |
| `400`  | Cliente errou a **regra de negocio** (pedido ja finalizado) |
| `401`  | Nao autenticado — **nao sei quem voce e**               |
| `403`  | Autenticado, mas **sem permissao** — sei quem voce e, e voce nao pode |
| `404`  | Nao existe                                              |
| `422`  | Cliente errou o **formato** — o Pydantic devolve isso sozinho |

A confusao classica e `401` vs `403`. Regra: **401 = falta credencial. 403 = credencial ok,
permissao nao.** Ver `orders_routes.py:_pedido_autorizado`.

E `400` vs `422`: `422` e formato (`"quantidade": "abc"` num campo `int`), `400` e
semantica (`quantidade` valida, mas o pedido ja foi finalizado). O Pydantic cuida do `422`
sem voce escrever nada.

---

## Pydantic

```python
from pydantic import BaseModel, EmailStr, Field

class ItemPedidoSchema(BaseModel):
    quantidade: int = Field(gt=0)          # gt, ge, lt, le
    senha: str = Field(min_length=6)       # min_length, max_length
    email: EmailStr                        # requer: pip install "pydantic[email]"
    obs: str | None = None                 # opcional

    model_config = {"from_attributes": True}   # le objeto SQLAlchemy, nao so dict
```

**`from_attributes` e o que permite `return pedido`** (um objeto SQLAlchemy) numa rota com
`response_model=PedidoResponse`. Sem ele, o Pydantic so aceita dict e estoura.

### Schema de entrada ≠ schema de saida

```python
class UsuarioSchema(BaseModel):      # ENTRADA: tem senha
    nome: str
    senha: str

class UsuarioResponse(BaseModel):    # SAIDA: NAO tem senha
    id: int
    nome: str
    model_config = {"from_attributes": True}
```

`response_model` **filtra** a resposta: campo que nao esta no schema nao sai, mesmo que o
objeto tenha. E a sua rede de seguranca contra vazar `senha`.

---

## Depends

```python
from fastapi import Depends

def pegar_sessao():
    session = SessionLocal()
    try:
        yield session          # o que vem depois do yield roda DEPOIS da resposta
    finally:
        session.close()        # roda ate se a rota levantar excecao

@router.get("/")
async def listar(session: Session = Depends(pegar_sessao)): ...
```

Dependencia e so uma funcao que o FastAPI chama antes da rota e cujo retorno ele injeta.
Serve pra nao repetir "abre sessao", "valida token", "confere admin" em toda rota.

**Empilhar dependencias** — `verificar_admin` reusa `verificar_token`:

```python
def verificar_token(token: str = Depends(oauth2_schema)) -> Usuario: ...

def verificar_admin(usuario: Usuario = Depends(verificar_token)) -> Usuario:
    if not usuario.admin:
        raise HTTPException(403, "So admin")
    return usuario
```

**Proteger o router inteiro** — nenhuma rota de `/pedidos` roda sem token:

```python
router = APIRouter(prefix="/pedidos", dependencies=[Depends(verificar_token)])
```

Use `dependencies=[...]` quando voce so quer o **efeito** (barrar). Use
`= Depends(...)` no parametro quando voce quer o **retorno** (o objeto `usuario`).

---

## SQLAlchemy (ORM)

```python
# Buscar
session.query(Pedido).filter(Pedido.id == 1).first()      # 1 ou None
session.query(Pedido).filter(Pedido.usuario_id == 3).all()  # lista
session.query(Pedido).all()

# Criar
p = Pedido(usuario_id=1)
session.add(p)
session.commit()
session.refresh(p)     # recarrega do banco -> agora p.id existe

# Atualizar: mude o atributo e commite. Nao tem "update()".
pedido.status = StatusPedido.CANCELADO
session.commit()

# Apagar
session.delete(item)
session.commit()
```

### `flush` vs `commit` vs `refresh`

Os tres confundem, e o projeto usa os tres:

| Metodo      | O que faz                                                        |
| ----------- | ---------------------------------------------------------------- |
| `flush()`   | Manda o SQL pro banco, **sem fechar a transacao**. Da pra desfazer. |
| `commit()`  | Confirma de vez. Nao tem volta.                                  |
| `refresh(x)`| Recarrega `x` do banco (pra pegar `id`, `default`, relacionamentos). |

Onde isso morde, em `adicionar_item`:

```python
session.add(item)
session.flush()          # sem isso, o item nao existe no banco...
session.refresh(pedido)  # ...e pedido.itens nao enxerga ele
pedido.calcular_preco()  # ai o total sairia errado
session.commit()
```

Tire o `flush()` e o preco fica desatualizado em um item. E o tipo de bug que passa no
teste feliz e quebra em producao.

---

## Auth (JWT)

```
1. POST /auth/login  { email, senha }
2. servidor confere bcrypt.checkpw(senha, hash_do_banco)
3. servidor devolve   { access_token, refresh_token }
4. cliente manda em toda request:  Authorization: Bearer <access_token>
5. servidor faz jwt.decode(token) -> pega o "sub" -> carrega o Usuario
```

O JWT **nao e criptografado, e assinado**. Qualquer um le o conteudo (cole em
<https://jwt.io>). O que ninguem consegue e **forjar** um sem a `SECRET_KEY`.
Consequencia pratica: **nunca ponha dado sensivel no payload do token.**

```python
payload = {
    "sub": str(id_usuario),                              # subject: quem e
    "exp": datetime.now(timezone.utc) + timedelta(...),  # a lib checa sozinha no decode
    "scope": "access_token",                             # access ou refresh
}
jwt.encode(payload, SECRET_KEY, algorithm="HS256")
```

**Por que dois tokens.** O access dura 30 min e vai em toda request (mais chance de
vazar em log, proxy, historico). O refresh dura 7 dias e so aparece na rota `/auth/refresh`.
Se o access vazar, o estrago expira em 30 min — e ele **nao** consegue gerar tokens novos,
porque `ler_token` confere o `scope`. Sem essa checagem de escopo, os dois tokens seriam a
mesma coisa e o refresh nao serviria pra nada.

---

## Erros

```python
from fastapi import HTTPException, status

raise HTTPException(
    status_code=status.HTTP_403_FORBIDDEN,
    detail="Voce nao tem permissao sobre este pedido",
)
```

**Nunca** entregue mensagens diferentes para "e-mail nao existe" e "senha errada":

```python
if not usuario or not verificar_senha(senha, usuario.senha):
    raise HTTPException(401, "Credenciais invalidas")   # a MESMA mensagem pros dois
```

Mensagens distintas viram **enumeracao de usuarios**: o atacante testa e-mails, ve qual
devolve "senha errada", e agora tem sua lista de clientes.

---

## Comandos

```bash
uvicorn main:app --reload            # dev (recarrega ao salvar)
python models.py                     # cria as tabelas
rm banco.db && python models.py      # recria do zero apos mudar model
pytest -v                            # testes
python -c "import secrets; print(secrets.token_hex(32))"   # gera SECRET_KEY
```

`/docs` (Swagger, interativo) e `/redoc` (leitura) saem de graca — voce nao escreveu
uma linha de documentacao pra isso. Eles sao gerados **dos seus type hints e schemas**.
E o principal motivo de tipar tudo.
