"""Testes de caracterização: gamification_service (EXP, níveis, conquistas, ranking)."""

from unittest.mock import MagicMock, patch

import pytest

from app.services.gamification_service import GamificationService


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


def _usuario_mock(uid="user_1", exp_total=0, conquistas=None):
    u = MagicMock()
    u.id = uid
    u.exp_total = exp_total
    u.conquistas = conquistas or []
    return u


@pytest.fixture
def mock_db():
    with patch("app.services.gamification_service.db") as mock_db:
        yield mock_db


def test_adicionar_exp_usuario_inexistente_retorna_false(mock_db):
    with patch("app.services.gamification_service.Usuario.get_by_id", return_value=None):
        resultado = GamificationService._adicionar_exp("user_x", 50, "teste")

    assert resultado is False
    mock_db.collection.assert_not_called()


def test_adicionar_exp_sucesso_usa_increment_e_atualiza_level(mock_db):
    usuario = _usuario_mock(exp_total=90)
    with patch("app.services.gamification_service.Usuario.get_by_id", return_value=usuario):
        resultado = GamificationService._adicionar_exp("user_1", 20, "Chamado Concluído no Prazo")

    assert resultado is True
    update_kwargs = mock_db.collection.return_value.document.return_value.update.call_args[0][0]
    assert update_kwargs["level"] == 2  # 90 + 20 = 110 -> nível 2
    assert "exp_total" in update_kwargs
    assert "exp_semanal" in update_kwargs


def test_adicionar_exp_erro_no_update_retorna_false(mock_db):
    usuario = _usuario_mock(exp_total=10)
    mock_db.collection.return_value.document.return_value.update.side_effect = RuntimeError(
        "firestore down"
    )
    with patch("app.services.gamification_service.Usuario.get_by_id", return_value=usuario):
        resultado = GamificationService._adicionar_exp("user_1", 20, "teste")

    assert resultado is False


def test_avaliar_resolucao_chamado_no_prazo_concede_50_pontos():
    with patch.object(GamificationService, "_adicionar_exp") as mock_add:
        GamificationService.avaliar_resolucao_chamado("user_1", {"atrasado": False})

    mock_add.assert_called_once_with("user_1", 50, "Chamado Concluído no Prazo")


def test_avaliar_resolucao_chamado_atrasado_concede_15_pontos():
    with patch.object(GamificationService, "_adicionar_exp") as mock_add:
        GamificationService.avaliar_resolucao_chamado("user_1", {"atrasado": True})

    mock_add.assert_called_once_with("user_1", 15, "Chamado Concluído (Atrasado)")


def test_avaliar_resolucao_chamado_engole_excecao_e_nao_propaga():
    with patch.object(GamificationService, "_adicionar_exp", side_effect=RuntimeError("boom")):
        GamificationService.avaliar_resolucao_chamado("user_1", {"atrasado": False})


def test_avaliar_atendimento_inicial_concede_10_pontos():
    with patch.object(GamificationService, "_adicionar_exp") as mock_add:
        GamificationService.avaliar_atendimento_inicial("user_1")

    mock_add.assert_called_once_with("user_1", 10, "Iniciou Atendimento de Chamado")


def test_resetar_ranking_semanal_pula_usuarios_ja_zerados(mock_db):
    doc_zerado = MagicMock(id="u1")
    doc_zerado.to_dict.return_value = {"exp_semanal": 0}
    doc_com_exp = MagicMock(id="u2")
    doc_com_exp.to_dict.return_value = {"exp_semanal": 30}

    mock_db.collection.return_value.stream.return_value = [doc_zerado, doc_com_exp]
    mock_batch = MagicMock()
    mock_db.batch.return_value = mock_batch

    resultado = GamificationService.resetar_ranking_semanal()

    assert resultado is True
    mock_batch.update.assert_called_once()
    mock_batch.commit.assert_called_once()


def test_resetar_ranking_semanal_erro_retorna_false(mock_db):
    mock_db.collection.return_value.stream.side_effect = RuntimeError("firestore down")

    resultado = GamificationService.resetar_ranking_semanal()

    assert resultado is False
