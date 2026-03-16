"""Testes do serviço de exportação Excel (exportador_excel.exportar_relatorio_completo)."""

import io

from app.services.excel_export_service import MAX_EXPORT_CHAMADOS, exportador_excel


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
