"""Testes do service de gates dinâmicos (gates_service.py)."""

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _limpar_cache_gates():
    """Garante que o cache de gates é limpo antes e depois de cada teste."""
    from app.cache import static_cache_delete

    static_cache_delete("gates_validos_set")
    yield
    static_cache_delete("gates_validos_set")


def _make_gate_mock(gate_pai: str, etapa: str, ordem: int = 1, ativo: bool = True):
    g = MagicMock()
    g.gate_pai = gate_pai
    g.etapa = etapa
    g.nome_pt = f"{gate_pai} - {etapa}"
    g.ordem = ordem
    g.ativo = ativo
    return g


# ── build_gate_subetapas ──────────────────────────────────────────────────────


def test_build_gate_subetapas_retorna_dict_do_firestore():
    """build_gate_subetapas agrupa gates por gate_pai quando Firestore retorna dados."""
    from app.services.gates_service import build_gate_subetapas

    gates = [
        _make_gate_mock("Gate 1", "Desmontagem", 1),
        _make_gate_mock("Gate 1", "Limpeza", 2),
        _make_gate_mock("Gate 2", "Forno", 1),
    ]

    with patch("app.services.gates_service.CategoriaGate") as mock_cls:
        mock_cls.get_all_ativos.return_value = gates
        result = build_gate_subetapas()

    assert "Gate 1" in result
    assert "Gate 2" in result
    assert "Gate 1 - Desmontagem" in result["Gate 1"]
    assert "Gate 1 - Limpeza" in result["Gate 1"]
    assert "Gate 2 - Forno" in result["Gate 2"]


def test_build_gate_subetapas_fallback_quando_firestore_vazio():
    """build_gate_subetapas usa GATE_SUBETAPAS estático quando Firestore vazio."""
    from app.services.gates_service import build_gate_subetapas

    with patch("app.services.gates_service.CategoriaGate") as mock_cls:
        mock_cls.get_all_ativos.return_value = []
        result = build_gate_subetapas()

    assert "Gate 1" in result
    assert "Gate 1 - Desmontagem" in result["Gate 1"]


def test_build_gate_subetapas_fallback_quando_excecao():
    """build_gate_subetapas usa fallback estático quando Firestore lança exceção."""
    from app.services.gates_service import build_gate_subetapas

    with patch("app.services.gates_service.CategoriaGate") as mock_cls:
        mock_cls.get_all_ativos.side_effect = Exception("Firestore down")
        result = build_gate_subetapas()

    assert "Gate 1" in result
    assert len(result) == 4  # Gate 1..4


def test_build_gate_subetapas_ignora_gates_sem_gate_pai():
    """build_gate_subetapas ignora gates legados sem gate_pai definido."""
    from app.services.gates_service import build_gate_subetapas

    gate_sem_pai = _make_gate_mock("", "Alguma etapa", 1)
    gate_sem_pai.gate_pai = None
    gate_com_pai = _make_gate_mock("Gate 1", "Desmontagem", 1)

    with patch("app.services.gates_service.CategoriaGate") as mock_cls:
        mock_cls.get_all_ativos.return_value = [gate_sem_pai, gate_com_pai]
        result = build_gate_subetapas()

    assert list(result.keys()) == ["Gate 1"]


# ── is_gate_valido ────────────────────────────────────────────────────────────


def test_is_gate_valido_na_retorna_true_sem_consultar_firestore():
    """is_gate_valido('N/A') retorna True imediatamente, sem chamar Firestore."""
    from app.services.gates_service import is_gate_valido

    with patch("app.services.gates_service.CategoriaGate") as mock_cls:
        result = is_gate_valido("N/A")
        mock_cls.get_all_ativos.assert_not_called()

    assert result is True


def test_is_gate_valido_valor_firestore_aceito():
    """is_gate_valido retorna True para gate presente no Firestore."""
    from app.services.gates_service import is_gate_valido

    gates = [_make_gate_mock("Gate 1", "Desmontagem")]

    with patch("app.services.gates_service.CategoriaGate") as mock_cls:
        mock_cls.get_all_ativos.return_value = gates
        assert is_gate_valido("Gate 1 - Desmontagem") is True


def test_is_gate_valido_valor_ausente_rejeitado():
    """is_gate_valido retorna False para valor que não existe no Firestore."""
    from app.services.gates_service import is_gate_valido

    gates = [_make_gate_mock("Gate 1", "Desmontagem")]

    with patch("app.services.gates_service.CategoriaGate") as mock_cls:
        mock_cls.get_all_ativos.return_value = gates
        assert is_gate_valido("Gate 99 - Inexistente") is False


def test_is_gate_valido_fallback_estatico_quando_firestore_vazio():
    """is_gate_valido usa lista estática quando Firestore vazio."""
    from app.services.gates_service import is_gate_valido

    with patch("app.services.gates_service.CategoriaGate") as mock_cls:
        mock_cls.get_all_ativos.return_value = []
        assert is_gate_valido("Gate 1 - Desmontagem") is True
        assert is_gate_valido("Gate 99") is False


def test_is_gate_valido_fallback_estatico_quando_excecao():
    """is_gate_valido usa fallback estático quando Firestore lança exceção."""
    from app.services.gates_service import is_gate_valido

    with patch("app.services.gates_service.CategoriaGate") as mock_cls:
        mock_cls.get_all_ativos.side_effect = Exception("db down")
        assert is_gate_valido("Gate 1 - Limpeza") is True
        assert is_gate_valido("Invalido") is False


def test_is_gate_valido_gate_pai_sem_subetapa_rejeitado():
    """'Gate 1' sem sub-etapa é rejeitado (não está no Firestore nem no estático)."""
    from app.services.gates_service import is_gate_valido

    gates = [_make_gate_mock("Gate 1", "Desmontagem")]

    with patch("app.services.gates_service.CategoriaGate") as mock_cls:
        mock_cls.get_all_ativos.return_value = gates
        assert is_gate_valido("Gate 1") is False


# ── F-22: cache TTL 5min ──────────────────────────────────────────────────────


def test_is_gate_valido_segunda_chamada_usa_cache_sem_re_fetch():
    """F-22: 2ª chamada a is_gate_valido não deve consultar Firestore novamente."""
    from app.services.gates_service import is_gate_valido

    gates = [_make_gate_mock("Gate 1", "Desmontagem")]

    with patch("app.services.gates_service.CategoriaGate") as mock_cls:
        mock_cls.get_all_ativos.return_value = gates
        r1 = is_gate_valido("Gate 1 - Desmontagem")
        r2 = is_gate_valido("Gate 1 - Desmontagem")

    assert r1 is True
    assert r2 is True
    mock_cls.get_all_ativos.assert_called_once()


def test_is_gate_valido_apos_invalidacao_re_consulta_firestore():
    """F-22: static_cache_delete('gates_validos_set') força nova leitura do Firestore."""
    from app.cache import static_cache_delete
    from app.services.gates_service import is_gate_valido

    gates = [_make_gate_mock("Gate 1", "Desmontagem")]

    with patch("app.services.gates_service.CategoriaGate") as mock_cls:
        mock_cls.get_all_ativos.return_value = gates
        is_gate_valido("Gate 1 - Desmontagem")  # popula cache
        static_cache_delete("gates_validos_set")  # invalida
        is_gate_valido("Gate 1 - Desmontagem")  # deve re-buscar

    assert mock_cls.get_all_ativos.call_count == 2
