"""TDD — scripts/executar_qa_escalonamento.py

Testa a estrutura do script QA Onda 6 (10 cenários ESC-*),
o contrato da interface (lista de 10 Resultado) e o exit code.
"""

import json
from unittest.mock import MagicMock, patch

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _mock_resultado(id_esc: str, status: str = "PASS") -> MagicMock:
    r = MagicMock()
    r.id_esc = id_esc
    r.status = status
    r.descricao = f"Cenário {id_esc}"
    r.detalhe = "detalhe mock"
    return r


# ─────────────────────────────────────────────────────────────────────────────
# Test 1 — executar_checks retorna lista com 10 itens
# ─────────────────────────────────────────────────────────────────────────────


def test_executar_qa_escalonamento_retorna_lista_com_10_itens():
    """executar_checks() deve retornar exatamente 10 Resultado."""
    import scripts.qa.executar_qa_escalonamento as m

    checks = [
        "check_esc_01",
        "check_esc_02",
        "check_esc_03",
        "check_esc_04",
        "check_esc_05",
        "check_esc_06",
        "check_esc_07",
        "check_esc_08",
        "check_esc_09",
        "check_esc_10",
    ]
    resultados_mock = [_mock_resultado(f"ESC-0{i + 1}") for i in range(10)]

    # Patch todos os checks individuais para retornar PASS imediato
    patches = {
        c: patch.object(m, c, return_value=resultados_mock[i]) for i, c in enumerate(checks[:9])
    }
    # check_esc_10 recebe app como argumento
    patch_10 = patch.object(m, "check_esc_10", return_value=resultados_mock[9])
    patch_app = patch.object(m, "_criar_app_testing", return_value=MagicMock())

    with patch_app, patch_10:
        for _c, p in patches.items():
            p.start()
        try:
            resultados = m.executar_checks()
        finally:
            for p in patches.values():
                p.stop()

    assert len(resultados) == 10


# ─────────────────────────────────────────────────────────────────────────────
# Test 2 — todos PASS com mocks (smoke)
# ─────────────────────────────────────────────────────────────────────────────


def test_executar_qa_escalonamento_todos_pass_com_mocks():
    """Com todos os checks mockados como PASS, nenhum deve ser FAIL ou SKIP."""
    import scripts.qa.executar_qa_escalonamento as m

    checks_names = [
        "check_esc_01",
        "check_esc_02",
        "check_esc_03",
        "check_esc_04",
        "check_esc_05",
        "check_esc_06",
        "check_esc_07",
        "check_esc_08",
        "check_esc_09",
    ]
    resultados_mock = [_mock_resultado(f"ESC-{i:02d}", "PASS") for i in range(1, 11)]

    patches = {
        c: patch.object(m, c, return_value=resultados_mock[i]) for i, c in enumerate(checks_names)
    }
    patch_10 = patch.object(m, "check_esc_10", return_value=resultados_mock[9])
    patch_app = patch.object(m, "_criar_app_testing", return_value=MagicMock())

    with patch_app, patch_10:
        for p in patches.values():
            p.start()
        try:
            resultados = m.executar_checks()
        finally:
            for p in patches.values():
                p.stop()

    assert all(r.status == "PASS" for r in resultados)
    assert not any(r.status == "FAIL" for r in resultados)


# ─────────────────────────────────────────────────────────────────────────────
# Test 3 — main() exit code 0 quando sem FAIL
# ─────────────────────────────────────────────────────────────────────────────


def test_main_exit_code_0_quando_sem_fail():
    """main() retorna 0 quando todos os checks são PASS."""
    import scripts.qa.executar_qa_escalonamento as m

    resultados_pass = [_mock_resultado(f"ESC-{i:02d}", "PASS") for i in range(1, 11)]

    with (
        patch.object(m, "executar_checks", return_value=resultados_pass),
        patch("sys.argv", ["executar_qa_escalonamento.py"]),
    ):
        exit_code = m.main()

    assert exit_code == 0


def test_main_exit_code_1_quando_tem_fail():
    """main() retorna 1 quando pelo menos um check é FAIL."""
    import scripts.qa.executar_qa_escalonamento as m

    resultados = [_mock_resultado(f"ESC-{i:02d}", "PASS") for i in range(1, 10)]
    resultados.append(_mock_resultado("ESC-10", "FAIL"))

    with (
        patch.object(m, "executar_checks", return_value=resultados),
        patch("sys.argv", ["executar_qa_escalonamento.py"]),
    ):
        exit_code = m.main()

    assert exit_code == 1


def test_main_saida_json_valida(capsys):
    """main() com --json produz JSON válido com as chaves esperadas."""

    import scripts.qa.executar_qa_escalonamento as m
    from scripts.qa.executar_qa_escalonamento import Resultado

    resultados_reais = [
        Resultado(id_esc=f"ESC-{i:02d}", descricao=f"Cenário {i}", status="PASS", detalhe="ok")
        for i in range(1, 11)
    ]

    with (
        patch.object(m, "executar_checks", return_value=resultados_reais),
        patch("sys.argv", ["executar_qa_escalonamento.py", "--json"]),
    ):
        m.main()

    captured = capsys.readouterr()
    data = json.loads(captured.out)

    assert "executado_em" in data
    assert "resumo" in data
    assert "resultados" in data
    assert data["resumo"]["total"] == 10
    assert data["resumo"]["pass"] == 10
    assert data["resumo"]["fail"] == 0
    assert len(data["resultados"]) == 10
