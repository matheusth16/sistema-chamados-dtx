"""Testes do GamificationService — EXP, levels e conquistas (badges) MVP.

Fase 2, Marco 10: _adicionar_exp/resetar_ranking_semanal rodam contra
Postgres real (db_session). O incremento atômico agora é um
UPDATE ... SET exp_total = exp_total + delta (sem transação Firestore
explícita) — o teste de concorrência prova a atomicidade com threads e
conexões físicas separadas, mesmo padrão de tests/test_services/
test_contadores_uso.py::test_relatorio_concorrencia_real_nao_ultrapassa_limite.
"""

import pytest

from app.models_usuario import Usuario
from app.services.gamification_service import GamificationService

pytestmark = pytest.mark.usefixtures("db_session")


def _criar_usuario(uid="user1", exp_total=0, exp_semanal=0, level=1, conquistas=None):
    u = Usuario(
        id=uid,
        email=f"{uid}@test.com",
        nome="Usuario Teste",
        exp_total=exp_total,
        exp_semanal=exp_semanal,
        level=level,
        conquistas=conquistas or [],
    )
    assert u.save()
    return u


# ── get_level_for_exp ─────────────────────────────────────────────────────────


def test_get_level_for_exp_nivel_1_com_zero():
    assert GamificationService.get_level_for_exp(0) == 1


def test_get_level_for_exp_nivel_2_com_100():
    assert GamificationService.get_level_for_exp(100) == 2


def test_get_level_for_exp_nivel_10_com_4500():
    assert GamificationService.get_level_for_exp(4500) == 10


def test_get_exp_for_next_level_retorna_100_para_exp_0():
    assert GamificationService.get_exp_for_next_level(0) == 100


def test_get_exp_for_next_level_nivel_maximo_retorna_exp_atual():
    assert GamificationService.get_exp_for_next_level(9999) == 9999


# ── _adicionar_exp ────────────────────────────────────────────────────────────


def test_adicionar_exp_atualiza_exp_e_level():
    _criar_usuario("user1", exp_total=50, level=1)

    result = GamificationService._adicionar_exp("user1", 60, "Chamado Concluído no Prazo")

    assert result is True
    atualizado = Usuario.get_by_id("user1")
    # exp_total incrementado atomicamente via UPDATE ... SET exp_total = exp_total + 60
    assert atualizado.exp_total == 110
    # level é calculado otimisticamente: 50 + 60 = 110 → nível 2
    assert atualizado.level == 2


def test_adicionar_exp_retorna_false_se_usuario_nao_existe():
    result = GamificationService._adicionar_exp("ghost", 50, "Concluído")

    assert result is False


def test_adicionar_exp_nao_usa_usuario_update():
    """_adicionar_exp deve atualizar via UPDATE atômico direto, não usuario.update()
    (que faria um set absoluto não-atômico, reabrindo o race condition F-14)."""
    u = _criar_usuario("user1", exp_total=50, level=1)
    chamado_update = []
    u.update = lambda **kw: chamado_update.append(kw)

    result = GamificationService._adicionar_exp("user1", 60, "Chamado Concluído no Prazo")

    assert result is True
    assert chamado_update == []


# ── conquistas (badges) MVP ───────────────────────────────────────────────────


def test_verificar_novas_conquistas_primeira_resolucao():
    novas = GamificationService._verificar_novas_conquistas(
        conquistas_atuais=[],
        motivo="Chamado Concluído no Prazo",
        novo_level=1,
        nova_exp_total=50,
    )
    assert "primeira_resolucao" in novas


def test_verificar_novas_conquistas_nao_duplica():
    novas = GamificationService._verificar_novas_conquistas(
        conquistas_atuais=["primeira_resolucao"],
        motivo="Chamado Concluído no Prazo",
        novo_level=1,
        nova_exp_total=50,
    )
    assert "primeira_resolucao" not in novas


def test_verificar_novas_conquistas_nivel_3():
    novas = GamificationService._verificar_novas_conquistas(
        conquistas_atuais=[],
        motivo="Iniciou Atendimento",
        novo_level=3,
        nova_exp_total=300,
    )
    assert "nivel_3" in novas


def test_verificar_novas_conquistas_nivel_5():
    novas = GamificationService._verificar_novas_conquistas(
        conquistas_atuais=["nivel_3"],
        motivo="Chamado Concluído no Prazo",
        novo_level=5,
        nova_exp_total=1000,
    )
    assert "nivel_5" in novas
    assert "nivel_3" not in novas


def test_verificar_novas_conquistas_cinco_resolucoes():
    novas = GamificationService._verificar_novas_conquistas(
        conquistas_atuais=["primeira_resolucao"],
        motivo="Chamado Concluído no Prazo",
        novo_level=2,
        nova_exp_total=250,
    )
    assert "cinco_resolucoes" in novas


def test_verificar_novas_conquistas_nivel_10():
    novas = GamificationService._verificar_novas_conquistas(
        conquistas_atuais=["nivel_3", "nivel_5"],
        motivo="Chamado Concluído no Prazo",
        novo_level=10,
        nova_exp_total=4500,
    )
    assert "nivel_10" in novas


def test_adicionar_exp_adiciona_conquista_primeira_resolucao():
    """_adicionar_exp deve registrar a conquista 'primeira_resolucao' no primeiro fechamento."""
    _criar_usuario("user1", exp_total=0, level=1, conquistas=[])

    GamificationService._adicionar_exp("user1", 50, "Chamado Concluído no Prazo")

    assert "primeira_resolucao" in Usuario.get_by_id("user1").conquistas


def test_adicionar_exp_exception_retorna_false(monkeypatch):
    """_adicionar_exp retorna False quando há exceção."""

    def _explode(cls, uid):
        raise Exception("err")

    monkeypatch.setattr(Usuario, "get_by_id", classmethod(_explode))

    result = GamificationService._adicionar_exp("user_err", 10, "motivo")

    assert result is False


# ── avaliar_resolucao_chamado ─────────────────────────────────────────────────


def test_avaliar_resolucao_no_prazo_concede_50_exp():
    _criar_usuario("user1", exp_total=0, level=1, conquistas=[])

    GamificationService.avaliar_resolucao_chamado("user1", {"atrasado": False})

    assert Usuario.get_by_id("user1").exp_total == 50


def test_avaliar_resolucao_atrasado_concede_15_exp():
    _criar_usuario("user1", exp_total=0, level=1, conquistas=[])

    GamificationService.avaliar_resolucao_chamado("user1", {"atrasado": True})

    assert Usuario.get_by_id("user1").exp_total == 15


# ── avaliar_atendimento_inicial ───────────────────────────────────────────────


def test_avaliar_atendimento_inicial_concede_10_exp():
    _criar_usuario("user1", exp_total=0, level=1, conquistas=[])

    GamificationService.avaliar_atendimento_inicial("user1")

    assert Usuario.get_by_id("user1").exp_total == 10


# ── resetar_ranking_semanal (S4-02 / F-27) ────────────────────────────────────


def test_resetar_ranking_semanal_zera_exp_semanal():
    """resetar_ranking_semanal zera exp_semanal de usuários com valor > 0."""
    _criar_usuario("u1", exp_semanal=50)
    _criar_usuario("u2", exp_semanal=0)

    result = GamificationService.resetar_ranking_semanal()

    assert result is True
    assert Usuario.get_by_id("u1").exp_semanal == 0
    assert Usuario.get_by_id("u2").exp_semanal == 0


def test_resetar_ranking_semanal_retorna_false_em_excecao(monkeypatch):
    """resetar_ranking_semanal retorna False quando o banco lança exceção."""
    from app.services import gamification_service

    def _explode():
        raise RuntimeError("banco indisponível")

    monkeypatch.setattr(gamification_service.db_module, "SessionLocal", _explode)

    result = GamificationService.resetar_ranking_semanal()

    assert result is False


def test_avaliar_resolucao_excecao_nao_propaga(monkeypatch):
    """avaliar_resolucao_chamado não propaga exceções — captura no logger."""

    def _explode(uid, pontos, motivo):
        raise Exception("db error")

    monkeypatch.setattr(GamificationService, "_adicionar_exp", staticmethod(_explode))

    GamificationService.avaliar_resolucao_chamado("user_exc", {})


# ── Concorrência (S2-02) ──────────────────────────────────────────────────────


def test_adicionar_exp_concorrencia_20_requests(db_engine, monkeypatch):
    """20 threads (conexões físicas separadas) somando +10 EXP cada: o UPDATE
    atômico garante que todos os deltas chegam, sem lost update — mesmo padrão
    de test_contadores_uso.py::test_relatorio_concorrencia_real_nao_ultrapassa_limite."""
    import threading

    from sqlalchemy import select, text
    from sqlalchemy.orm import scoped_session, sessionmaker

    from app.db.models.usuario import UsuarioRow
    from app.services import gamification_service

    pontos = 10
    num_threads = 20
    total_esperado = pontos * num_threads  # 200

    real_factory = scoped_session(
        sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)
    )
    monkeypatch.setattr(gamification_service.db_module, "SessionLocal", real_factory)

    # Cria o usuário via a mesma conexão real usada pelas threads concorrentes
    # (não a savepoint isolada de db_session) — senão as threads, em conexões
    # físicas separadas, não enxergariam a linha (visibilidade entre transações).
    with real_factory() as session, session.begin():
        session.add(
            UsuarioRow(id="user_concorrente", email="uc@test.com", nome="UC", exp_total=0, level=1)
        )
    real_factory.remove()

    results = []
    results_lock = threading.Lock()

    def run():
        try:
            ok = GamificationService._adicionar_exp(
                "user_concorrente", pontos, "Iniciou Atendimento"
            )
            with results_lock:
                results.append(ok)
        finally:
            real_factory.remove()

    try:
        threads = [threading.Thread(target=run) for _ in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert all(results), "Todos os 20 requests devem retornar True"

        with real_factory() as session:
            exp_final = session.execute(
                select(UsuarioRow.exp_total).where(UsuarioRow.id == "user_concorrente")
            ).scalar_one()
        real_factory.remove()

        assert exp_final == total_esperado, (
            f"UPDATE atômico deve acumular {total_esperado} EXP; obtido {exp_final}"
        )
    finally:
        with db_engine.connect() as conn:
            conn.execute(text("DELETE FROM usuarios WHERE id = 'user_concorrente'"))
            conn.commit()
