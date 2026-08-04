"""Testes de caracterização: gamification_service (EXP, níveis, conquistas,
ranking). Fase 2, Marco 10: _adicionar_exp/resetar_ranking_semanal rodam
contra Postgres real (db_session) — UPDATE ... SET x = x + delta no lugar
do antigo Increment() do Firestore."""

import pytest

from app.models_usuario import Usuario
from app.services.gamification_service import GamificationService

pytestmark = pytest.mark.usefixtures("db_session")


def _criar_usuario(uid="user_1", exp_total=0, exp_semanal=0, level=1, conquistas=None):
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


@pytest.mark.parametrize(
    "exp,nivel_esperado",
    [
        (0, 1),
        (99, 1),
        (100, 2),
        (299, 2),
        (300, 3),
        (4499, 9),
        (4500, 10),
        (999999, 10),
    ],
)
def test_get_level_for_exp(exp, nivel_esperado):
    assert GamificationService.get_level_for_exp(exp) == nivel_esperado


def test_get_exp_for_next_level_retorna_proximo_patamar():
    assert GamificationService.get_exp_for_next_level(50) == 100
    assert GamificationService.get_exp_for_next_level(150) == 300


def test_get_exp_for_next_level_no_nivel_maximo_retorna_proprio_exp():
    assert GamificationService.get_exp_for_next_level(5000) == 5000


def test_verificar_novas_conquistas_nivel_3():
    novas = GamificationService._verificar_novas_conquistas(
        conquistas_atuais=[], motivo="Chamado Concluído no Prazo", novo_level=3, nova_exp_total=300
    )
    assert "nivel_3" in novas


def test_verificar_novas_conquistas_nao_repete_conquista_existente():
    novas = GamificationService._verificar_novas_conquistas(
        conquistas_atuais=["nivel_3"],
        motivo="Chamado Concluído no Prazo",
        novo_level=3,
        nova_exp_total=300,
    )
    assert "nivel_3" not in novas


def test_verificar_novas_conquistas_primeira_resolucao():
    novas = GamificationService._verificar_novas_conquistas(
        conquistas_atuais=[], motivo="Chamado Concluído no Prazo", novo_level=1, nova_exp_total=50
    )
    assert "primeira_resolucao" in novas


def test_verificar_novas_conquistas_cinco_resolucoes_exige_250_exp():
    novas = GamificationService._verificar_novas_conquistas(
        conquistas_atuais=["primeira_resolucao"],
        motivo="Chamado Concluído no Prazo",
        novo_level=3,
        nova_exp_total=250,
    )
    assert "cinco_resolucoes" in novas


# ── _adicionar_exp (Postgres real) ────────────────────────────────────────────


def test_adicionar_exp_usuario_inexistente_retorna_false():
    resultado = GamificationService._adicionar_exp("nao_existe", 50, "teste")

    assert resultado is False


def test_adicionar_exp_sucesso_usa_update_atomico_e_atualiza_level():
    _criar_usuario("user_1", exp_total=90, exp_semanal=90)

    resultado = GamificationService._adicionar_exp("user_1", 20, "Chamado Concluído no Prazo")

    assert resultado is True
    atualizado = Usuario.get_by_id("user_1")
    assert atualizado.exp_total == 110  # 90 + 20
    assert atualizado.exp_semanal == 110  # 90 + 20
    assert atualizado.level == 2  # 110 -> nível 2


def test_adicionar_exp_erro_no_update_retorna_false(monkeypatch):
    from app.services import gamification_service

    _criar_usuario("user_1", exp_total=10)

    def _explode():
        raise RuntimeError("banco indisponível")

    monkeypatch.setattr(gamification_service.db_module, "SessionLocal", _explode)

    resultado = GamificationService._adicionar_exp("user_1", 20, "teste")

    assert resultado is False


# ── avaliar_resolucao_chamado / avaliar_atendimento_inicial (delegação pura) ──


def test_avaliar_resolucao_chamado_no_prazo_concede_50_pontos(monkeypatch):
    chamadas = []
    monkeypatch.setattr(
        GamificationService,
        "_adicionar_exp",
        staticmethod(lambda uid, pontos, motivo: chamadas.append((uid, pontos, motivo))),
    )

    GamificationService.avaliar_resolucao_chamado("user_1", {"atrasado": False})

    assert chamadas == [("user_1", 50, "Chamado Concluído no Prazo")]


def test_avaliar_resolucao_chamado_atrasado_concede_15_pontos(monkeypatch):
    chamadas = []
    monkeypatch.setattr(
        GamificationService,
        "_adicionar_exp",
        staticmethod(lambda uid, pontos, motivo: chamadas.append((uid, pontos, motivo))),
    )

    GamificationService.avaliar_resolucao_chamado("user_1", {"atrasado": True})

    assert chamadas == [("user_1", 15, "Chamado Concluído (Atrasado)")]


def test_avaliar_resolucao_chamado_engole_excecao_e_nao_propaga(monkeypatch):
    def _explode(uid, pontos, motivo):
        raise RuntimeError("boom")

    monkeypatch.setattr(GamificationService, "_adicionar_exp", staticmethod(_explode))

    GamificationService.avaliar_resolucao_chamado("user_1", {"atrasado": False})


def test_avaliar_atendimento_inicial_concede_10_pontos(monkeypatch):
    chamadas = []
    monkeypatch.setattr(
        GamificationService,
        "_adicionar_exp",
        staticmethod(lambda uid, pontos, motivo: chamadas.append((uid, pontos, motivo))),
    )

    GamificationService.avaliar_atendimento_inicial("user_1")

    assert chamadas == [("user_1", 10, "Iniciou Atendimento de Chamado")]


# ── resetar_ranking_semanal (Postgres real) ───────────────────────────────────


def test_resetar_ranking_semanal_pula_usuarios_ja_zerados():
    _criar_usuario("u1", exp_semanal=0)
    _criar_usuario("u2", exp_semanal=30)

    resultado = GamificationService.resetar_ranking_semanal()

    assert resultado is True
    assert Usuario.get_by_id("u1").exp_semanal == 0
    assert Usuario.get_by_id("u2").exp_semanal == 0


def test_resetar_ranking_semanal_erro_retorna_false(monkeypatch):
    from app.services import gamification_service

    def _explode():
        raise RuntimeError("banco indisponível")

    monkeypatch.setattr(gamification_service.db_module, "SessionLocal", _explode)

    resultado = GamificationService.resetar_ranking_semanal()

    assert resultado is False
