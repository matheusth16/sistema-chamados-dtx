"""
Testes do modelo GrupoRL (Fase 2 — Postgres real).

Substitui a suíte anterior baseada em mock do Firestore. get_or_create() foi
reescrito como upsert atômico (INSERT ... ON CONFLICT DO NOTHING) — o teste de
concorrência real prova que a race condition do antigo check-then-act
(get_by_rl_codigo + add separados) foi eliminada.
"""

import threading

import pytest

pytestmark = pytest.mark.usefixtures("db_session")


# ── Construção ─────────────────────────────────────────────────────────────────


def test_init_strip_rl_codigo():
    """GrupoRL.__init__ faz strip no rl_codigo."""
    from app.models_grupo_rl import GrupoRL

    g = GrupoRL(rl_codigo="  RL-001  ")
    assert g.rl_codigo == "RL-001"


def test_to_dict_contem_campos_esperados():
    """to_dict retorna os campos esperados."""
    from app.models_grupo_rl import GrupoRL

    g = GrupoRL(rl_codigo="RL-001", criado_por_id="u1", area="TI")
    d = g.to_dict()

    assert d["rl_codigo"] == "RL-001"
    assert d["criado_por_id"] == "u1"
    assert d["area"] == "TI"
    assert "criado_em" in d


def test_from_dict_cria_grupo_correto():
    """from_dict cria GrupoRL com campos corretos."""
    from app.models_grupo_rl import GrupoRL

    g = GrupoRL.from_dict(
        {"rl_codigo": "RL-999", "criado_por_id": "u2", "area": "Manutencao"},
        id=7,
    )

    assert g.id == 7
    assert g.rl_codigo == "RL-999"
    assert g.area == "Manutencao"


def test_from_dict_dados_vazios_lanca_valueerror():
    """from_dict com dict vazio/None lança ValueError."""
    from app.models_grupo_rl import GrupoRL

    with pytest.raises(ValueError):
        GrupoRL.from_dict({})


# ── get_by_rl_codigo ──────────────────────────────────────────────────────────


def test_get_by_rl_codigo_vazio_retorna_none(app):
    """get_by_rl_codigo com rl_codigo vazio retorna None sem consultar o banco."""
    from app.models_grupo_rl import GrupoRL

    assert GrupoRL.get_by_rl_codigo("") is None


def test_get_by_rl_codigo_encontrado_retorna_grupo(app):
    """get_by_rl_codigo encontra a linha e retorna GrupoRL."""
    from app.models_grupo_rl import GrupoRL

    GrupoRL.get_or_create("RL-001", criado_por_id="u1", area="TI")

    result = GrupoRL.get_by_rl_codigo("RL-001")

    assert result is not None
    assert result.rl_codigo == "RL-001"


def test_get_by_rl_codigo_nao_encontrado_retorna_none(app):
    """get_by_rl_codigo sem linha correspondente retorna None."""
    from app.models_grupo_rl import GrupoRL

    assert GrupoRL.get_by_rl_codigo("RL-999-NAO-EXISTE") is None


# ── get_or_create ─────────────────────────────────────────────────────────────


def test_get_or_create_rl_codigo_vazio_lanca_valueerror(app):
    """get_or_create com rl_codigo vazio lança ValueError."""
    from app.models_grupo_rl import GrupoRL

    with pytest.raises(ValueError):
        GrupoRL.get_or_create("")


def test_get_or_create_existente_retorna_grupo_existente(app):
    """get_or_create quando grupo já existe retorna o existente, sem duplicar."""
    from app.models_grupo_rl import GrupoRL

    primeiro = GrupoRL.get_or_create("RL-001", criado_por_id="u1", area="TI")
    segundo = GrupoRL.get_or_create("RL-001", criado_por_id="u2", area="Outra")

    assert segundo.id == primeiro.id
    # Dados do primeiro registro são preservados — get_or_create não atualiza
    assert segundo.criado_por_id == "u1"


def test_get_or_create_novo_cria_e_retorna(app):
    """get_or_create quando grupo não existe cria novo e retorna."""
    from app.models_grupo_rl import GrupoRL

    result = GrupoRL.get_or_create("RL-002", criado_por_id="u1", area="TI")

    assert result.id is not None
    assert result.rl_codigo == "RL-002"


def test_get_or_create_concorrente_cria_so_um_grupo(db_engine, monkeypatch):
    """Concorrência real (threads + conexões físicas separadas do engine real):
    get_or_create disparado ao mesmo tempo pro mesmo rl_codigo cria só 1 grupo —
    prova que a race condition do antigo check-then-act (Firestore) foi
    eliminada pelo upsert atômico (INSERT ... ON CONFLICT DO NOTHING).

    Não usa a sessão de savepoint da fixture db_session: uma única conexão
    física compartilhada não pode ser usada por múltiplas threads ao mesmo
    tempo (psycopg não é thread-safe por conexão) e não exercitaria o
    travamento real do Postgres. Usa uma sessão nova por thread, cada uma com
    sua própria conexão do engine real — e limpa a linha criada ao final,
    já que esses commits são reais (não fazem parte de nenhum savepoint)."""
    from sqlalchemy import text
    from sqlalchemy.orm import scoped_session, sessionmaker

    from app.models_grupo_rl import GrupoRL

    real_factory = scoped_session(
        sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    )
    monkeypatch.setattr("app.db.SessionLocal", real_factory)

    resultados = []
    erros = []

    def _tentar_criar():
        try:
            r = GrupoRL.get_or_create("RL-CONCORRENTE-XYZ", criado_por_id="u1", area="TI")
            resultados.append(r.id)
        except Exception as e:  # pragma: no cover - só se algo der muito errado
            erros.append(e)
        finally:
            real_factory.remove()

    threads = [threading.Thread(target=_tentar_criar) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    with db_engine.connect() as conn:
        conn.execute(text("DELETE FROM grupos_rl WHERE rl_codigo = 'RL-CONCORRENTE-XYZ'"))
        conn.commit()

    assert not erros
    assert len(resultados) == 10
    assert len(set(resultados)) == 1  # todas as threads viram o MESMO id
