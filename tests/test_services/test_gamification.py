"""Testes do GamificationService — EXP, levels e conquistas (badges) MVP."""

from unittest.mock import MagicMock, patch


def _make_usuario(exp_total=0, exp_semanal=0, level=1, conquistas=None):
    u = MagicMock()
    u.exp_total = exp_total
    u.exp_semanal = exp_semanal
    u.level = level
    u.conquistas = conquistas if conquistas is not None else []
    u.update = MagicMock(return_value=True)
    return u


# ── get_level_for_exp ─────────────────────────────────────────────────────────


def test_get_level_for_exp_nivel_1_com_zero():
    from app.services.gamification_service import GamificationService

    assert GamificationService.get_level_for_exp(0) == 1


def test_get_level_for_exp_nivel_2_com_100():
    from app.services.gamification_service import GamificationService

    assert GamificationService.get_level_for_exp(100) == 2


def test_get_level_for_exp_nivel_10_com_4500():
    from app.services.gamification_service import GamificationService

    assert GamificationService.get_level_for_exp(4500) == 10


def test_get_exp_for_next_level_retorna_100_para_exp_0():
    from app.services.gamification_service import GamificationService

    assert GamificationService.get_exp_for_next_level(0) == 100


def test_get_exp_for_next_level_nivel_maximo_retorna_exp_atual():
    from app.services.gamification_service import GamificationService

    assert GamificationService.get_exp_for_next_level(9999) == 9999


# ── _adicionar_exp ────────────────────────────────────────────────────────────


def test_adicionar_exp_atualiza_exp_e_level():
    from app.services.gamification_service import GamificationService

    u = _make_usuario(exp_total=50, level=1)
    with patch("app.services.gamification_service.Usuario.get_by_id", return_value=u):
        result = GamificationService._adicionar_exp("user1", 60, "Chamado Concluído no Prazo")
    assert result is True
    call_kwargs = u.update.call_args[1] if u.update.call_args[1] else {}
    call_positional = u.update.call_args[0] if u.update.call_args[0] else ()
    gamif = call_kwargs.get("gamification") or (call_positional[0] if call_positional else {})
    assert gamif["exp_total"] == 110
    assert gamif["level"] == 2


def test_adicionar_exp_retorna_false_se_usuario_nao_existe():
    from app.services.gamification_service import GamificationService

    with patch("app.services.gamification_service.Usuario.get_by_id", return_value=None):
        result = GamificationService._adicionar_exp("ghost", 50, "Concluído")
    assert result is False


# ── conquistas (badges) MVP ───────────────────────────────────────────────────


def test_verificar_novas_conquistas_primeira_resolucao():
    from app.services.gamification_service import GamificationService

    novas = GamificationService._verificar_novas_conquistas(
        conquistas_atuais=[],
        motivo="Chamado Concluído no Prazo",
        novo_level=1,
        nova_exp_total=50,
    )
    assert "primeira_resolucao" in novas


def test_verificar_novas_conquistas_nao_duplica():
    from app.services.gamification_service import GamificationService

    novas = GamificationService._verificar_novas_conquistas(
        conquistas_atuais=["primeira_resolucao"],
        motivo="Chamado Concluído no Prazo",
        novo_level=1,
        nova_exp_total=50,
    )
    assert "primeira_resolucao" not in novas


def test_verificar_novas_conquistas_nivel_3():
    from app.services.gamification_service import GamificationService

    novas = GamificationService._verificar_novas_conquistas(
        conquistas_atuais=[],
        motivo="Iniciou Atendimento",
        novo_level=3,
        nova_exp_total=300,
    )
    assert "nivel_3" in novas


def test_verificar_novas_conquistas_nivel_5():
    from app.services.gamification_service import GamificationService

    novas = GamificationService._verificar_novas_conquistas(
        conquistas_atuais=["nivel_3"],
        motivo="Chamado Concluído no Prazo",
        novo_level=5,
        nova_exp_total=1000,
    )
    assert "nivel_5" in novas
    assert "nivel_3" not in novas


def test_verificar_novas_conquistas_cinco_resolucoes():
    from app.services.gamification_service import GamificationService

    novas = GamificationService._verificar_novas_conquistas(
        conquistas_atuais=["primeira_resolucao"],
        motivo="Chamado Concluído no Prazo",
        novo_level=2,
        nova_exp_total=250,
    )
    assert "cinco_resolucoes" in novas


def test_verificar_novas_conquistas_nivel_10():
    from app.services.gamification_service import GamificationService

    novas = GamificationService._verificar_novas_conquistas(
        conquistas_atuais=["nivel_3", "nivel_5"],
        motivo="Chamado Concluído no Prazo",
        novo_level=10,
        nova_exp_total=4500,
    )
    assert "nivel_10" in novas


def test_adicionar_exp_adiciona_conquista_primeira_resolucao():
    """_adicionar_exp deve registrar a conquista 'primeira_resolucao' no primeiro fechamento."""
    from app.services.gamification_service import GamificationService

    u = _make_usuario(exp_total=0, level=1, conquistas=[])
    with patch("app.services.gamification_service.Usuario.get_by_id", return_value=u):
        GamificationService._adicionar_exp("user1", 50, "Chamado Concluído no Prazo")

    call_kwargs = u.update.call_args[1] if u.update.call_args[1] else {}
    call_positional = u.update.call_args[0] if u.update.call_args[0] else ()
    gamif = call_kwargs.get("gamification") or (call_positional[0] if call_positional else {})
    assert "primeira_resolucao" in gamif.get("conquistas", [])


def test_adicionar_exp_exception_retorna_false():
    """_adicionar_exp retorna False quando há exceção."""
    from app.services.gamification_service import GamificationService

    with patch("app.services.gamification_service.Usuario.get_by_id", side_effect=Exception("err")):
        result = GamificationService._adicionar_exp("user_err", 10, "motivo")
    assert result is False


# ── avaliar_resolucao_chamado ─────────────────────────────────────────────────


def test_avaliar_resolucao_no_prazo_concede_50_exp():
    from app.services.gamification_service import GamificationService

    u = _make_usuario(exp_total=0, level=1, conquistas=[])
    with patch("app.services.gamification_service.Usuario.get_by_id", return_value=u):
        GamificationService.avaliar_resolucao_chamado("user1", {"atrasado": False})

    call_kwargs = u.update.call_args[1] if u.update.call_args[1] else {}
    call_positional = u.update.call_args[0] if u.update.call_args[0] else ()
    gamif = call_kwargs.get("gamification") or (call_positional[0] if call_positional else {})
    assert gamif.get("exp_total") == 50


def test_avaliar_resolucao_atrasado_concede_15_exp():
    from app.services.gamification_service import GamificationService

    u = _make_usuario(exp_total=0, level=1, conquistas=[])
    with patch("app.services.gamification_service.Usuario.get_by_id", return_value=u):
        GamificationService.avaliar_resolucao_chamado("user1", {"atrasado": True})

    call_kwargs = u.update.call_args[1] if u.update.call_args[1] else {}
    call_positional = u.update.call_args[0] if u.update.call_args[0] else ()
    gamif = call_kwargs.get("gamification") or (call_positional[0] if call_positional else {})
    assert gamif.get("exp_total") == 15


# ── avaliar_atendimento_inicial ───────────────────────────────────────────────


def test_avaliar_atendimento_inicial_concede_10_exp():
    from app.services.gamification_service import GamificationService

    u = _make_usuario(exp_total=0, level=1, conquistas=[])
    with patch("app.services.gamification_service.Usuario.get_by_id", return_value=u):
        GamificationService.avaliar_atendimento_inicial("user1")

    call_kwargs = u.update.call_args[1] if u.update.call_args[1] else {}
    call_positional = u.update.call_args[0] if u.update.call_args[0] else ()
    gamif = call_kwargs.get("gamification") or (call_positional[0] if call_positional else {})
    assert gamif.get("exp_total") == 10


def test_avaliar_resolucao_excecao_nao_propaga():
    """avaliar_resolucao_chamado não propaga exceções — captura no logger (linhas 150-151)."""
    from unittest.mock import patch

    from app.services.gamification_service import GamificationService

    with patch.object(GamificationService, "_adicionar_exp", side_effect=Exception("db error")):
        GamificationService.avaliar_resolucao_chamado("user_exc", {})
