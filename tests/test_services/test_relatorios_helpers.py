"""Testes dos helpers de ordenação e paginação de métricas de relatórios."""

from app.services.dashboard_service import (
    ordenar_metricas_areas,
    ordenar_metricas_supervisores,
    preparar_metricas_paginadas,
)

# ---------------------------------------------------------------------------
# ordenar_metricas_supervisores
# ---------------------------------------------------------------------------

SUP_A = {
    "supervisor_nome": "Ana",
    "area": "Manutencao",
    "total_chamados": 10,
    "carga_atual": 3,
    "taxa_resolucao_percentual": 80.0,
    "tempo_medio_resolucao_horas": 5.0,
    "percentual_dentro_sla": 90.0,
}
SUP_B = {
    "supervisor_nome": "Bruno",
    "area": "TI",
    "total_chamados": 5,
    "carga_atual": 8,
    "taxa_resolucao_percentual": 60.0,
    "tempo_medio_resolucao_horas": 12.0,
    "percentual_dentro_sla": None,
}
SUP_C = {
    "supervisor_nome": "Carlos",
    "area": "Qualidade",
    "total_chamados": 20,
    "carga_atual": 1,
    "taxa_resolucao_percentual": 95.0,
    "tempo_medio_resolucao_horas": 2.0,
    "percentual_dentro_sla": 70.0,
}


def test_ordenar_supervisores_por_total_desc():
    result = ordenar_metricas_supervisores([SUP_A, SUP_B, SUP_C], "total", asc=False)
    assert result[0]["total_chamados"] == 20


def test_ordenar_supervisores_por_total_asc():
    result = ordenar_metricas_supervisores([SUP_A, SUP_B, SUP_C], "total", asc=True)
    assert result[0]["total_chamados"] == 5


def test_ordenar_supervisores_por_carga():
    result = ordenar_metricas_supervisores([SUP_A, SUP_B, SUP_C], "carga", asc=False)
    assert result[0]["carga_atual"] == 8


def test_ordenar_supervisores_por_nome():
    result = ordenar_metricas_supervisores([SUP_B, SUP_A, SUP_C], "nome", asc=True)
    assert result[0]["supervisor_nome"] == "Ana"


def test_ordenar_supervisores_por_area():
    result = ordenar_metricas_supervisores([SUP_B, SUP_A, SUP_C], "area", asc=True)
    assert result[0]["area"] == "Manutencao"


def test_ordenar_supervisores_por_sla_none_fica_no_final_asc():
    """Ao ordenar asc (pior primeiro), supervisores sem SLA ficam no fim (sem dado = último)."""
    result = ordenar_metricas_supervisores([SUP_A, SUP_B, SUP_C], "sla", asc=True)
    # Ascending: (False, -90) < (False, -70) < (True, 0) → A, C, B — None por último
    assert result[-1]["supervisor_nome"] == "Bruno"


def test_ordenar_supervisores_campo_desconhecido_retorna_lista_inalterada():
    lista = [SUP_A, SUP_B, SUP_C]
    result = ordenar_metricas_supervisores(lista, "campo_inexistente", asc=True)
    assert result == lista


# ---------------------------------------------------------------------------
# ordenar_metricas_areas
# ---------------------------------------------------------------------------

AREA_A = {
    "area": "Manutencao",
    "total_chamados": 15,
    "abertos": 4,
    "taxa_resolucao_percentual": 70.0,
    "tempo_medio_resolucao_horas": 8.0,
}
AREA_B = {
    "area": "TI",
    "total_chamados": 5,
    "abertos": 2,
    "taxa_resolucao_percentual": 90.0,
    "tempo_medio_resolucao_horas": 3.0,
}


def test_ordenar_areas_por_total_desc():
    result = ordenar_metricas_areas([AREA_A, AREA_B], "total", asc=False)
    assert result[0]["total_chamados"] == 15


def test_ordenar_areas_por_abertos_asc():
    result = ordenar_metricas_areas([AREA_A, AREA_B], "abertos", asc=True)
    assert result[0]["abertos"] == 2


def test_ordenar_areas_por_area_nome():
    result = ordenar_metricas_areas([AREA_B, AREA_A], "area", asc=True)
    assert result[0]["area"] == "Manutencao"


def test_ordenar_areas_campo_desconhecido_retorna_lista_inalterada():
    lista = [AREA_A, AREA_B]
    result = ordenar_metricas_areas(lista, "campo_inexistente", asc=True)
    assert result == lista


# ---------------------------------------------------------------------------
# preparar_metricas_paginadas
# ---------------------------------------------------------------------------


def _make_items(n):
    return [{"total_chamados": i, "area": f"Area{i}"} for i in range(n)]


def test_preparar_metricas_paginadas_primeira_pagina():
    items = _make_items(10)
    result = preparar_metricas_paginadas(items, "total", False, 1, 3, ordenar_metricas_areas)
    assert len(result["items"]) == 3
    assert result["total"] == 10
    assert result["total_paginas"] == 4
    assert result["pagina"] == 1


def test_preparar_metricas_paginadas_pagina_alem_do_limite_clampeia():
    items = _make_items(5)
    result = preparar_metricas_paginadas(items, "total", False, 99, 3, ordenar_metricas_areas)
    assert result["pagina"] == 2  # 2 páginas; clampeia para última


def test_preparar_metricas_paginadas_pagina_negativa_clampeia_para_1():
    items = _make_items(5)
    result = preparar_metricas_paginadas(items, "total", False, -5, 3, ordenar_metricas_areas)
    assert result["pagina"] == 1


def test_preparar_metricas_paginadas_lista_vazia():
    result = preparar_metricas_paginadas([], "total", False, 1, 10, ordenar_metricas_areas)
    assert result["items"] == []
    assert result["total"] == 0
    assert result["total_paginas"] == 1
    assert result["pagina"] == 1


def test_preparar_metricas_paginadas_items_full_contem_lista_ordenada():
    """items_full deve conter todos os itens (para gráficos), já ordenados."""
    items = _make_items(6)
    result = preparar_metricas_paginadas(items, "total", True, 1, 3, ordenar_metricas_areas)
    assert len(result["items_full"]) == 6
    # Ordenado asc por total_chamados → primeiro deve ser 0
    assert result["items_full"][0]["total_chamados"] == 0
