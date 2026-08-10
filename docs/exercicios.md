# Exercicios

Doze desafios em cima deste projeto, do mais simples ao mais chato. Gabarito no fim —
**tente antes de olhar**, o ganho esta em travar e destravar sozinho.

Depois de cada um: `pytest -v` tem que continuar verde. Se quebrou, voce mudou contrato.

---

## Basico

### 1. Rota de perfil
Crie `GET /auth/perfil/{id_usuario}`. Retorna o usuario. Regra: usuario comum so ve o
proprio perfil; admin ve qualquer um.
*Dica: `verificar_token` te da o usuario logado. Compare com o `id_usuario` da URL.*

### 2. Desativar conta
`PATCH /auth/{id_usuario}/desativar` — so admin. Seta `ativo = False`.
*Depois teste: o usuario desativado ainda consegue usar um token que ele pegou antes?
Olhe `dependencies.py:_usuario_do_token`. Por que a checagem de `ativo` esta la, e nao
so no login?*

### 3. Paginacao
`GET /pedidos/?limite=10&pagina=1`.
*Dica: `.limit(n).offset((pagina - 1) * n)`. Valide com `Query(10, ge=1, le=100)`.*

### 4. Filtrar por status
`GET /pedidos/?status=PENDENTE`. Parametro opcional.
*Dica: tipe como `StatusPedido | None = None` e o Pydantic ja rejeita valor invalido.*

---

## Modelagem (o miolo)

### 5. Data do pedido
Adicione `criado_em` a `Pedido`, preenchido sozinho.
*Dica: `Column(DateTime, default=lambda: datetime.now(timezone.utc))`.*
*Pegadinha: `default=datetime.now(timezone.utc)` (sem lambda) congela a hora em que o
**modulo foi importado**. Todo pedido nasce com a mesma data. Entenda por que.*
*E lembre: `create_all` nao adiciona coluna em tabela existente. `rm banco.db`.*

### 6. Tabela de Produto
Hoje `sabor`, `tamanho` e `preco_unitario` sao texto solto — nada impede
`{"sabor": "Calabreza", "preco_unitario": 0.01}`. Crie `Produto` (id, nome, tamanho,
preco) e faca `ItemPedido` referenciar `produto_id`.

**A pergunta que importa:** voce deve **remover** `preco_unitario` de `ItemPedido` e
puxar de `produto.preco`? Releia a secao 5 de [modelagem-de-dados.md](modelagem-de-dados.md)
antes de responder. (Resposta no gabarito — e nao, nao deve.)

### 7. Endereco de entrega
Adicione endereco ao pedido. Decida: coluna solta em `Pedido`, ou tabela `Endereco` com
FK pro `Usuario`?
*Se for tabela separada: o usuario troca de casa. O pedido antigo tem que continuar
mostrando o endereco velho. Como voce garante isso? (Mesma logica do preco congelado.)*

### 8. Cupom de desconto
Tabela `Cupom` (codigo unique, percentual, validade, usos_maximos). Aplicar em
`POST /pedidos/{id}/cupom`.
*Onde entra no `calcular_preco()`? Guarde `preco_bruto` e `preco_final` ou so o final?
Argumente a partir do que um cliente veria numa nota fiscal.*

### 9. Constraint de integridade
Impeca no **banco** (nao na rota) que `quantidade <= 0`.
*Dica: `CheckConstraint("quantidade > 0")` no `__table_args__`.*
*Reflita: voce ja valida isso no Pydantic (`Field(gt=0)`). Por que fazer nos dois lugares?*

### 10. Alembic
Instale o Alembic e transforme a mudanca do exercicio 5 numa migration de verdade —
sem apagar `banco.db`.
```bash
pip install alembic && alembic init alembic
# alembic/env.py: sqlalchemy.url + target_metadata = Base.metadata
alembic revision --autogenerate -m "adiciona criado_em em pedido"
alembic upgrade head
```
*Abra o arquivo gerado em `alembic/versions/`. Entenda `upgrade()` e `downgrade()`.
Rode `alembic downgrade -1` e veja a coluna sumir.*

---

## Avancado

### 11. Testes
Escreva testes para os exercicios 1-4 em `test_api.py`. Use `TestClient`.
*Melhoria real no setup atual: os testes hoje batem no `banco.db` de verdade. Troque por
um banco em memoria (`sqlite:///:memory:`) com `app.dependency_overrides[pegar_sessao]`.
Assim o teste nao suja seu banco de dev e roda do zero toda vez.*

### 12. Refresh token de uso unico
Hoje um refresh token vale ate expirar, e pode ser usado infinitas vezes. Se ele vazar,
o atacante mantem acesso por 7 dias. Implemente **rotacao**: cada uso invalida o anterior.
*Dica: precisa de estado no servidor — uma tabela `RefreshToken` (jti, usuario_id,
revogado). Ponha um `jti` (id unico) no payload do JWT e confira contra a tabela.*
*Isso quebra a promessa "JWT e stateless". Voce concorda com a troca? Por que?*

---
---

# Gabarito

<details>
<summary><b>1. Rota de perfil</b></summary>

```python
@auth_routes.get("/perfil/{id_usuario}", response_model=UsuarioResponse)
async def perfil(
    id_usuario: int,
    session: Session = Depends(pegar_sessao),
    usuario: Usuario = Depends(verificar_token),
):
    if usuario.id != id_usuario and not usuario.admin:
        raise HTTPException(403, "Sem permissao")

    alvo = session.query(Usuario).filter(Usuario.id == id_usuario).first()
    if not alvo:
        raise HTTPException(404, "Usuario nao encontrado")
    return alvo
```
Mesmo padrao de `orders_routes._pedido_autorizado`: **checa permissao antes de buscar o
recurso, ou logo depois — mas sempre antes de devolver.**
</details>

<details>
<summary><b>2. Desativar conta</b></summary>

```python
@auth_routes.patch("/{id_usuario}/desativar", response_model=UsuarioResponse)
async def desativar(
    id_usuario: int,
    session: Session = Depends(pegar_sessao),
    admin: Usuario = Depends(verificar_admin),   # a dependencia ja barra nao-admin
):
    alvo = session.query(Usuario).filter(Usuario.id == id_usuario).first()
    if not alvo:
        raise HTTPException(404, "Usuario nao encontrado")
    alvo.ativo = False
    session.commit()
    session.refresh(alvo)
    return alvo
```

**A resposta da pergunta:** o token continua **valido** — ele e assinado e nao expirou,
nada no JWT mudou. Se voce checasse `ativo` so no login, o desativado seguiria usando a
API por ate 30 min. Por isso `_usuario_do_token` recarrega o usuario do banco e checa
`ativo` **a cada request**. Esse e o preco de JWT stateless: revogar exige uma consulta
ao banco em algum ponto.
</details>

<details>
<summary><b>3. Paginacao</b></summary>

```python
@order_routes.get("/", response_model=list[PedidoResponse])
async def listar_pedidos(
    limite: int = Query(10, ge=1, le=100),
    pagina: int = Query(1, ge=1),
    session: Session = Depends(pegar_sessao),
    usuario: Usuario = Depends(verificar_token),
):
    query = session.query(Pedido)
    if not usuario.admin:
        query = query.filter(Pedido.usuario_id == usuario.id)
    return query.limit(limite).offset((pagina - 1) * limite).all()
```
O `le=100` nao e frescura: sem teto, um `?limite=999999999` vira DoS de graca.
</details>

<details>
<summary><b>4. Filtrar por status</b></summary>

```python
async def listar_pedidos(
    status_filtro: StatusPedido | None = None,
    ...
):
    query = session.query(Pedido)
    if not usuario.admin:
        query = query.filter(Pedido.usuario_id == usuario.id)
    if status_filtro:
        query = query.filter(Pedido.status == status_filtro)
    return query.all()
```
Tipar como `StatusPedido | None` faz o FastAPI devolver `422` sozinho em
`?status_filtro=banana`, **e** listar os valores validos no `/docs`. Se fosse `str`, voce
teria que validar na mao e documentar na mao.
</details>

<details>
<summary><b>5. Data do pedido</b></summary>

```python
from datetime import datetime, timezone
from sqlalchemy import DateTime

criado_em = Column(
    "criado_em",
    DateTime,
    default=lambda: datetime.now(timezone.utc),   # a lambda e obrigatoria
    nullable=False,
)
```

**Por que a lambda.** `default=datetime.now(timezone.utc)` **executa a chamada na hora do
import** e guarda o valor. O `default` vira uma constante: todo pedido criado durante a
vida do processo nasce com o horario em que voce subiu o servidor. Com `lambda`, o
SQLAlchemy chama a funcao a cada insert.

Mesma pegadinha do argumento default mutavel em Python (`def f(x=[])`) — a expressao do
default e avaliada **uma vez**, na definicao.

Nao esqueca de por `criado_em: datetime` em `PedidoResponse`, senao o campo existe no
banco e nunca aparece na API.
</details>

<details>
<summary><b>6. Tabela de Produto</b></summary>

```python
class Produto(Base):
    __tablename__ = "produtos"
    id = Column(Integer, primary_key=True, autoincrement=True)
    nome = Column(String, nullable=False)
    tamanho = Column(String, nullable=False)
    preco = Column(Float, nullable=False)      # preco ATUAL, de tabela
    ativo = Column(Boolean, default=True)

class ItemPedido(Base):
    produto_id = Column(Integer, ForeignKey("produtos.id"), nullable=False)
    preco_unitario = Column(Float, nullable=False)   # <- CONTINUA AQUI
    produto = relationship("Produto")
```

**Nao remova `preco_unitario`.** Os dois campos parecem redundantes e nao sao:

- `Produto.preco` = quanto custa **hoje**.
- `ItemPedido.preco_unitario` = quanto custou **naquele pedido**.

Se voce apagar o `preco_unitario` e puxar de `produto.preco` no `calcular_preco()`, um
reajuste de tabela **reescreve o valor de todos os pedidos passados**. O cliente pagou
R$ 50, abre o historico mes que vem e ve R$ 60. Em nota fiscal, isso e ilegal.

A rota deve **copiar** o preco na hora de criar o item:
```python
produto = session.query(Produto).filter(Produto.id == item_schema.produto_id).first()
item = ItemPedido(..., preco_unitario=produto.preco)   # congela agora
```
Repare que o cliente nao manda mais o preco — some a chance de mandar `0.01`.
</details>

<details>
<summary><b>7. Endereco de entrega</b></summary>

Tabela `Endereco` (FK pro `Usuario`) **para o cadastro** — o usuario tem varios enderecos
salvos. Mas o `Pedido` **nao** guarda `endereco_id`: ele **copia** o texto do endereco no
momento da compra.

```python
class Pedido(Base):
    endereco_entrega = Column(String, nullable=False)   # snapshot, texto
```

Se voce guardar `endereco_id`, o usuario muda de casa e **o pedido antigo passa a dizer
que foi entregue no endereco novo**. Voce destruiu o historico de entrega.

Mesma regra do preco: **dado historico se copia, nao se referencia.** Se voce percebeu
isso sozinho, entendeu a secao 5 do doc de modelagem.
</details>

<details>
<summary><b>8. Cupom</b></summary>

```python
class Cupom(Base):
    __tablename__ = "cupons"
    id = Column(Integer, primary_key=True)
    codigo = Column(String, unique=True, index=True, nullable=False)
    percentual = Column(Float, nullable=False)
    validade = Column(DateTime, nullable=False)
    usos_maximos = Column(Integer, default=1)
    usos_atuais = Column(Integer, default=0)
```

Em `Pedido`, guarde **os dois** precos e o percentual aplicado:
```python
preco_bruto = Column(Float, default=0.0)
desconto_percentual = Column(Float, default=0.0)
preco = Column(Float, default=0.0)          # o final, ja com desconto

def calcular_preco(self):
    self.preco_bruto = sum(i.preco_unitario * i.quantidade for i in self.itens)
    self.preco = self.preco_bruto * (1 - self.desconto_percentual / 100)
    return self.preco
```

**Por que guardar os dois:** olhe uma nota fiscal de verdade. Ela mostra subtotal,
desconto e total — as tres linhas. Se voce so guarda o final, nao consegue reconstruir a
conta, nem responder "quanto de desconto eu dei esse mes". E se o cupom for editado depois
(`percentual` de 10 vira 20), o pedido antigo recalcularia errado — por isso o
`desconto_percentual` tambem e **copiado** pro pedido, nao lido do cupom. De novo: dado
historico se copia.
</details>

<details>
<summary><b>9. CheckConstraint</b></summary>

```python
from sqlalchemy import CheckConstraint

class ItemPedido(Base):
    __tablename__ = "itens_pedido"
    __table_args__ = (
        CheckConstraint("quantidade > 0", name="check_quantidade_positiva"),
        CheckConstraint("preco_unitario > 0", name="check_preco_positivo"),
    )
```

**Por que validar nos dois lugares.** Sao defesas contra coisas diferentes:

- O **Pydantic** protege contra o *cliente* mandar lixo. Da erro bonito (`422`, com o campo
  e a mensagem). Mas so roda quando o dado entra **pela API**.
- O **CheckConstraint** protege contra *voce*. Um script de migracao, um `python -i` as
  duas da manha, uma rota nova que voce escreveu e esqueceu o `Field(gt=0)` — nada disso
  passa pelo Pydantic. Passa pelo banco.

O banco e a **ultima** linha de defesa e a unica que nenhum caminho de codigo contorna.
Regra: **valide na borda para dar erro bom, e no banco para garantir que e verdade.**
</details>

<details>
<summary><b>11. Testes com banco em memoria</b></summary>

```python
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
        poolclass=StaticPool,   # sem isso, cada conexao pega um banco :memory: NOVO
    )
    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(bind=engine, expire_on_commit=False)

    def pegar_sessao_teste():
        session = TestSession()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[pegar_sessao] = pegar_sessao_teste
    yield TestClient(app)
    app.dependency_overrides.clear()      # limpa, senao vaza pro proximo teste
```

`dependency_overrides` e o motivo pelo qual voce injeta a sessao com `Depends` em vez de
abrir ela dentro da rota: **o que e injetado pode ser trocado no teste.** Rota que faz
`session = SessionLocal()` na primeira linha e rota que voce nao consegue testar sem banco.

O `StaticPool` e a pegadinha: `sqlite:///:memory:` cria um banco novo **por conexao**.
Sem ele, voce cria as tabelas numa conexao e a rota abre outra, vazia.
</details>

<details>
<summary><b>12. Refresh token rotativo</b></summary>

```python
import uuid

class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    id = Column(Integer, primary_key=True)
    jti = Column(String, unique=True, index=True, nullable=False)  # id unico do token
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    revogado = Column(Boolean, default=False)
```

Ponha `"jti": str(uuid.uuid4())` no payload, salve o `jti` na tabela ao emitir, e em
`/auth/refresh`: confira que o `jti` existe e nao esta revogado → revogue → emita um par
novo com `jti` novo.

**Sobre a troca.** Sim, isso quebra o "JWT e stateless" — voce agora bate no banco pra
validar o refresh. Mas repare: **so no refresh**, que acontece a cada 30 min. O access
token, que vai em *toda* request, continua validando so pela assinatura.

Isso e o desenho certo. "Stateless" nunca foi o objetivo — o objetivo e **nao consultar o
banco no caminho quente**. Voce paga uma consulta a cada 30 min e ganha a capacidade de
revogar sessao, que e o que `logout` de verdade exige. Quem defende JWT 100% stateless
geralmente nao implementou logout ainda.

*Bonus:* se um `jti` ja revogado for reapresentado, isso e sinal de token roubado (alguem
esta usando uma copia antiga). A resposta certa e revogar **todos** os tokens daquele
usuario e forcar login.
</details>

claude --resume 310393e5-a4b3-4db5-ab42-fd14009ea0fd
