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


def _mock_db():
    return MagicMock()


def _get_gamif_update(mock_db):
    """Extrai o dict passado para db.collection('usuarios').document().update()."""
    return mock_db.collection.return_value.document.return_value.update.call_args[0][0]


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
    from google.cloud.firestore_v1 import Increment as FirestoreIncrement

    from app.services.gamification_service import GamificationService

    u = _make_usuario(exp_total=50, level=1)
    mock_db = _mock_db()
    with (
        patch("app.services.gamification_service.Usuario.get_by_id", return_value=u),
        patch("app.services.gamification_service.db", mock_db),
    ):
        result = GamificationService._adicionar_exp("user1", 60, "Chamado Concluído no Prazo")
    assert result is True
    data = _get_gamif_update(mock_db)
    # exp_total usa Increment atômico — verifica delta, não valor absoluto
    assert data["exp_total"] == FirestoreIncrement(60)
    # level é calculado otimisticamente: 50 + 60 = 110 → nível 2
    assert data["level"] == 2


def test_adicionar_exp_retorna_false_se_usuario_nao_existe():
    from app.services.gamification_service import GamificationService

    with patch("app.services.gamification_service.Usuario.get_by_id", return_value=None):
        result = GamificationService._adicionar_exp("ghost", 50, "Concluído")
    assert result is False


def test_adicionar_exp_usa_increment_atomico():
    """_adicionar_exp deve usar Increment no Firestore direto, não usuario.update().

    Race condition (F-14): sem Increment, dois requests simultâneos leem o mesmo
    exp_total e ambos escrevem o valor somado → apenas um incremento persiste.
    Com Increment, o Firestore aplica o incremento atomicamente no servidor.
    """
    from app.services.gamification_service import GamificationService

    u = _make_usuario(exp_total=50, level=1)
    mock_db = _mock_db()
    with (
        patch("app.services.gamification_service.Usuario.get_by_id", return_value=u),
        patch("app.services.gamification_service.db", mock_db),
    ):
        result = GamificationService._adicionar_exp("user1", 60, "Chamado Concluído no Prazo")

    assert result is True
    # db.collection("usuarios").document("user1").update() deve ser chamado
    mock_db.collection.assert_called_with("usuarios")
    mock_db.collection.return_value.document.assert_called_with("user1")
    mock_db.collection.return_value.document.return_value.update.assert_called_once()
    # exp_total no dict de update deve ser um Increment (não inteiro absoluto)
    data = _get_gamif_update(mock_db)
    assert not isinstance(data.get("exp_total"), int), (
        "exp_total deve ser Increment(pontos) para evitar race condition, não valor absoluto"
    )
    # usuario.update() (método da classe) NÃO deve ser chamado
    u.update.assert_not_called()


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
    mock_db = _mock_db()
    with (
        patch("app.services.gamification_service.Usuario.get_by_id", return_value=u),
        patch("app.services.gamification_service.db", mock_db),
    ):
        GamificationService._adicionar_exp("user1", 50, "Chamado Concluído no Prazo")

    data = _get_gamif_update(mock_db)
    assert "primeira_resolucao" in data.get("conquistas", [])


def test_adicionar_exp_exception_retorna_false():
    """_adicionar_exp retorna False quando há exceção."""
    from app.services.gamification_service import GamificationService

    with patch("app.services.gamification_service.Usuario.get_by_id", side_effect=Exception("err")):
        result = GamificationService._adicionar_exp("user_err", 10, "motivo")
    assert result is False


# ── avaliar_resolucao_chamado ─────────────────────────────────────────────────


def test_avaliar_resolucao_no_prazo_concede_50_exp():
    from google.cloud.firestore_v1 import Increment as FirestoreIncrement

    from app.services.gamification_service import GamificationService

    u = _make_usuario(exp_total=0, level=1, conquistas=[])
    mock_db = _mock_db()
    with (
        patch("app.services.gamification_service.Usuario.get_by_id", return_value=u),
        patch("app.services.gamification_service.db", mock_db),
    ):
        GamificationService.avaliar_resolucao_chamado("user1", {"atrasado": False})

    data = _get_gamif_update(mock_db)
    assert data["exp_total"] == FirestoreIncrement(50)


def test_avaliar_resolucao_atrasado_concede_15_exp():
    from google.cloud.firestore_v1 import Increment as FirestoreIncrement

    from app.services.gamification_service import GamificationService

    u = _make_usuario(exp_total=0, level=1, conquistas=[])
    mock_db = _mock_db()
    with (
        patch("app.services.gamification_service.Usuario.get_by_id", return_value=u),
        patch("app.services.gamification_service.db", mock_db),
    ):
        GamificationService.avaliar_resolucao_chamado("user1", {"atrasado": True})

    data = _get_gamif_update(mock_db)
    assert data["exp_total"] == FirestoreIncrement(15)


# ── avaliar_atendimento_inicial ───────────────────────────────────────────────


def test_avaliar_atendimento_inicial_concede_10_exp():
    from google.cloud.firestore_v1 import Increment as FirestoreIncrement

    from app.services.gamification_service import GamificationService

    u = _make_usuario(exp_total=0, level=1, conquistas=[])
    mock_db = _mock_db()
    with (
        patch("app.services.gamification_service.Usuario.get_by_id", return_value=u),
        patch("app.services.gamification_service.db", mock_db),
    ):
        GamificationService.avaliar_atendimento_inicial("user1")

    data = _get_gamif_update(mock_db)
    assert data["exp_total"] == FirestoreIncrement(10)


# ── resetar_ranking_semanal (S4-02 / F-27) ────────────────────────────────────


def test_resetar_ranking_semanal_zera_exp_semanal():
    """resetar_ranking_semanal zera exp_semanal de usuários com valor > 0 via batch."""
    from app.services.gamification_service import GamificationService

    doc1 = MagicMock()
    doc1.id = "u1"
    doc1.to_dict.return_value = {"exp_semanal": 50}
    doc2 = MagicMock()
    doc2.id = "u2"
    doc2.to_dict.return_value = {"exp_semanal": 0}

    mock_db = _mock_db()
    mock_batch = MagicMock()
    mock_db.batch.return_value = mock_batch
    mock_db.collection.return_value.stream.return_value = iter([doc1, doc2])

    with patch("app.services.gamification_service.db", mock_db):
        result = GamificationService.resetar_ranking_semanal()

    assert result is True
    assert mock_batch.update.call_count == 1
    call_args = mock_batch.update.call_args[0]
    assert call_args[1] == {"exp_semanal": 0}
    mock_batch.commit.assert_called_once()


def test_resetar_ranking_semanal_ignora_usuarios_com_zero():
    """resetar_ranking_semanal não chama batch.update para usuários com exp_semanal == 0."""
    from app.services.gamification_service import GamificationService

    doc = MagicMock()
    doc.id = "u_zero"
    doc.to_dict.return_value = {"exp_semanal": 0}

    mock_db = _mock_db()
    mock_batch = MagicMock()
    mock_db.batch.return_value = mock_batch
    mock_db.collection.return_value.stream.return_value = iter([doc])

    with patch("app.services.gamification_service.db", mock_db):
        result = GamificationService.resetar_ranking_semanal()

    assert result is True
    mock_batch.update.assert_not_called()
    mock_batch.commit.assert_not_called()


def test_resetar_ranking_semanal_retorna_false_em_excecao():
    """resetar_ranking_semanal retorna False quando Firestore lança exceção."""
    from app.services.gamification_service import GamificationService

    mock_db = _mock_db()
    mock_db.collection.return_value.stream.side_effect = Exception("Firestore error")

    with patch("app.services.gamification_service.db", mock_db):
        result = GamificationService.resetar_ranking_semanal()

    assert result is False


def test_avaliar_resolucao_excecao_nao_propaga():
    """avaliar_resolucao_chamado não propaga exceções — captura no logger (linhas 150-151)."""
    from unittest.mock import patch

    from app.services.gamification_service import GamificationService

    with patch.object(GamificationService, "_adicionar_exp", side_effect=Exception("db error")):
        GamificationService.avaliar_resolucao_chamado("user_exc", {})


# ── Concorrência (S2-02) ──────────────────────────────────────────────────────


def test_adicionar_exp_concorrencia_20_requests():
    """20 chamadas simultâneas de +10 EXP: Increment garante que todos os deltas chegam.

    Sem Increment (read-then-write), requests concorrentes sobrescrevem uns aos outros.
    Com Increment, o Firestore aplica cada delta atomicamente no servidor.
    O mock simula isso com um contador protegido por lock; o serial_lock reflete
    a serialização interna do Firestore para as escritas Increment.
    """
    import threading

    from google.cloud.firestore_v1 import Increment as FirestoreIncrement

    from app.services.gamification_service import GamificationService

    pontos = 10
    num_threads = 20
    total_esperado = pontos * num_threads  # 200

    # Simula o acumulador do Firestore: cada Increment(10) adiciona ao total
    total_acumulado = [0]
    acc_lock = threading.Lock()

    def mock_db_update(update_dict):
        inc = update_dict.get("exp_total")
        if isinstance(inc, FirestoreIncrement):
            with acc_lock:
                total_acumulado[0] += inc.value

    mock_db = _mock_db()
    mock_db.collection.return_value.document.return_value.update.side_effect = mock_db_update

    u = _make_usuario(exp_total=0, level=1)
    results = []
    results_lock = threading.Lock()

    def run():
        ok = GamificationService._adicionar_exp("user1", pontos, "Iniciou Atendimento")
        with results_lock:
            results.append(ok)

    # Patches aplicados uma vez no nível do teste — não por thread (thread-unsafe)
    with (
        patch("app.services.gamification_service.Usuario.get_by_id", return_value=u),
        patch("app.services.gamification_service.db", mock_db),
    ):
        threads = [threading.Thread(target=run) for _ in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    assert all(results), "Todos os 20 requests devem retornar True"
    assert total_acumulado[0] == total_esperado, (
        f"Increment deve acumular {total_esperado} EXP; obtido {total_acumulado[0]}"
    )
