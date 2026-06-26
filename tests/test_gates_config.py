"""Testes unitários de app/gates_config.py."""

import pytest

# ── GATE_PAI_OPCOES ────────────────────────────────────────────────────────────


def test_gate_pai_opcoes_contem_na_e_gates():
    from app.gates_config import GATE_PAI_OPCOES

    valores = [v for v, _ in GATE_PAI_OPCOES]
    assert "N/A" in valores
    assert "Gate 1" in valores
    assert "Gate 4" in valores


def test_gate_pai_opcoes_tem_labels():
    from app.gates_config import GATE_PAI_OPCOES

    for _valor, label in GATE_PAI_OPCOES:
        assert isinstance(label, str) and label


# ── GATE_SUBETAPAS ─────────────────────────────────────────────────────────────


def test_gate_subetapas_contem_quatro_gates():
    from app.gates_config import GATE_SUBETAPAS

    for i in range(1, 5):
        assert f"Gate {i}" in GATE_SUBETAPAS, f"Gate {i} ausente em GATE_SUBETAPAS"


def test_gate_subetapas_gate1_tem_quatro_etapas():
    from app.gates_config import GATE_SUBETAPAS

    etapas = GATE_SUBETAPAS["Gate 1"]
    assert len(etapas) == 4
    assert any("Desmontagem" in e for e in etapas)
    assert any("Limpeza" in e for e in etapas)
    assert any("Remoção de Tinta" in e for e in etapas)
    assert any("Reconciliação" in e for e in etapas)


def test_gate_subetapas_gate2_tem_quatro_etapas():
    from app.gates_config import GATE_SUBETAPAS

    etapas = GATE_SUBETAPAS["Gate 2"]
    assert len(etapas) == 4
    assert any("Forno" in e for e in etapas)
    assert any("FPI" in e for e in etapas)
    assert any("MPI" in e for e in etapas)
    assert any("Inspeção" in e for e in etapas)


def test_gate_subetapas_gate3_tem_quatro_etapas():
    from app.gates_config import GATE_SUBETAPAS

    etapas = GATE_SUBETAPAS["Gate 3"]
    assert len(etapas) == 4
    assert any("Galvanoplastia" in e for e in etapas)
    assert any("Usinagem" in e for e in etapas)
    assert any("Bucha" in e for e in etapas)
    assert any("Pintura" in e for e in etapas)


def test_gate_subetapas_gate4_tem_quatro_etapas():
    from app.gates_config import GATE_SUBETAPAS

    etapas = GATE_SUBETAPAS["Gate 4"]
    assert len(etapas) == 4
    assert any("Inspeção de Partes" in e for e in etapas)
    assert any("Montagem" in e for e in etapas)
    assert any("Testes" in e for e in etapas)
    assert any("Inspeção Final" in e for e in etapas)


def test_gate_subetapas_valores_tem_prefixo_gate():
    """Cada valor canônico deve iniciar com 'Gate N - '."""
    from app.gates_config import GATE_SUBETAPAS

    for gate_key, etapas in GATE_SUBETAPAS.items():
        for etapa in etapas:
            assert etapa.startswith(gate_key + " - "), f"'{etapa}' não começa com '{gate_key} - '"


# ── gate_valor_completo ────────────────────────────────────────────────────────


def test_gate_valor_completo_monta_string():
    from app.gates_config import gate_valor_completo

    resultado = gate_valor_completo("Gate 1", "Desmontagem")
    assert resultado == "Gate 1 - Desmontagem"


def test_gate_valor_completo_na_retorna_na():
    from app.gates_config import gate_valor_completo

    resultado = gate_valor_completo("N/A", "")
    assert resultado == "N/A"


# ── todos_valores_gate_validos ─────────────────────────────────────────────────


def test_todos_valores_gate_validos_retorna_16_valores_mais_na():
    from app.gates_config import todos_valores_gate_validos

    valores = todos_valores_gate_validos()
    assert "N/A" in valores
    assert len(valores) == 17  # N/A + 4 gates × 4 etapas


def test_todos_valores_gate_validos_contem_desmontagem():
    from app.gates_config import todos_valores_gate_validos

    assert "Gate 1 - Desmontagem" in todos_valores_gate_validos()


def test_todos_valores_gate_validos_contem_inspecao_final():
    from app.gates_config import todos_valores_gate_validos

    assert "Gate 4 - Inspeção Final" in todos_valores_gate_validos()


# ── is_gate_valido ─────────────────────────────────────────────────────────────


def test_is_gate_valido_na_aceito():
    from app.gates_config import is_gate_valido

    assert is_gate_valido("N/A") is True


@pytest.mark.parametrize(
    "valor",
    [
        "Gate 1 - Desmontagem",
        "Gate 1 - Limpeza",
        "Gate 1 - Remoção de Tinta",
        "Gate 1 - Reconciliação",
        "Gate 2 - Forno",
        "Gate 3 - Galvanoplastia",
        "Gate 4 - Inspeção Final",
    ],
)
def test_is_gate_valido_valores_completos_aceitos(valor):
    from app.gates_config import is_gate_valido

    assert is_gate_valido(valor) is True, f"'{valor}' deveria ser válido"


@pytest.mark.parametrize(
    "valor",
    [
        "Gate 1",
        "Gate 2",
        "Gate 3",
        "Gate 4",
        "",
        "gate1",
        "Gate 5",
        "N/A extra",
    ],
)
def test_is_gate_valido_valores_invalidos_rejeitados(valor):
    from app.gates_config import is_gate_valido

    assert is_gate_valido(valor) is False, f"'{valor}' não deveria ser válido"
