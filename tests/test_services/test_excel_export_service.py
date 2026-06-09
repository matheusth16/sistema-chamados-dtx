"""Testes do serviço de exportação Excel (exportador_excel.exportar_relatorio_completo)."""

import io

import pytest

from app.services.excel_export_service import MAX_EXPORT_CHAMADOS, _safe_cell, exportador_excel


def test_max_export_chamados_constante():
    """MAX_EXPORT_CHAMADOS está definido e é inteiro positivo."""
    assert MAX_EXPORT_CHAMADOS > 0
    assert isinstance(MAX_EXPORT_CHAMADOS, int)


def test_exportar_relatorio_completo_lista_vazia_retorna_bytes():
    """exportar_relatorio_completo com lista vazia de chamados retorna BytesIO (arquivo xlsx)."""
    output = exportador_excel.exportar_relatorio_completo(
        chamados=[],
        metricas_gerais={},
        metricas_supervisores=[],
        filtros_aplicados={},
    )
    assert isinstance(output, io.BytesIO)
    data = output.getvalue()
    assert len(data) > 0
    assert data[:2] == b"PK"


def test_exportar_relatorio_completo_com_chamado_mock_retorna_bytes():
    """exportar_relatorio_completo com um Chamado real retorna BytesIO sem exceção."""
    from app.models import Chamado

    chamado = Chamado(
        id="c1",
        numero_chamado="2026-001",
        categoria="Manutencao",
        tipo_solicitacao="Corretiva",
        descricao="Teste",
        responsavel="João",
        responsavel_id="u1",
        solicitante_id="s1",
        solicitante_nome="Maria",
        area="Manutencao",
        status="Aberto",
        prioridade=1,
        rl_codigo=None,
        gate=None,
        impacto=None,
        anexo=None,
        anexos=[],
        data_abertura=None,
        data_conclusao=None,
    )
    output = exportador_excel.exportar_relatorio_completo(
        chamados=[chamado],
        metricas_gerais={"total": 1, "abertos": 1},
        metricas_supervisores=[{"supervisor_nome": "João", "total_chamados": 1}],
        filtros_aplicados={},
    )
    assert isinstance(output, io.BytesIO)
    assert len(output.getvalue()) > 0


# ── Testes de segurança: formula injection ────────────────────────────────────


@pytest.mark.parametrize(
    "valor_entrada,esperado_prefixo",
    [
        ('=HYPERLINK("evil.com","click")', "'"),
        ("+1", "'"),
        ("-DROP TABLE", "'"),
        ("@SUM(A1:A10)", "'"),
        ("\tDATA", "'"),
        ("\rNEWLINE", "'"),
    ],
    ids=["igual", "mais", "menos", "arroba", "tab", "cr"],
)
def test_safe_cell_neutraliza_formula(valor_entrada, esperado_prefixo):
    """_safe_cell deve prefixar com ' strings que iniciam com char de fórmula."""
    resultado = _safe_cell(valor_entrada)
    assert isinstance(resultado, str)
    assert resultado.startswith(esperado_prefixo)
    assert valor_entrada in resultado


@pytest.mark.parametrize(
    "valor_seguro",
    ["texto normal", "2026-001", "Concluído", 42, None, 3.14, ""],
    ids=["texto", "numero_chamado", "status", "int", "none", "float", "vazio"],
)
def test_safe_cell_nao_altera_valores_seguros(valor_seguro):
    """_safe_cell não deve modificar valores que não iniciam com char de fórmula."""
    assert _safe_cell(valor_seguro) == valor_seguro
