"""Testes do serviço de A/B testing determinístico (AB-001)."""


def test_get_variante_e_deterministica():
    """Mesma entrada sempre retorna mesma variante."""
    from app.services.ab_service import get_variante

    v1 = get_variante("uid-123", "AB-001")
    v2 = get_variante("uid-123", "AB-001")
    assert v1 == v2


def test_get_variante_retorna_a_ou_b():
    """A variante retornada é sempre 'A' ou 'B'."""
    from app.services.ab_service import get_variante

    variante = get_variante("uid-xyz", "AB-001")
    assert variante in ("A", "B")


def test_get_variante_distribui_50_50():
    """Com 1000 UIDs distintos, distribuição entre 40–60% para 'B'."""
    from app.services.ab_service import get_variante

    resultados = [get_variante(f"uid-{i}", "AB-001") for i in range(1000)]
    pct_b = resultados.count("B") / 1000
    assert 0.40 <= pct_b <= 0.60, f"Distribuição fora de 40–60%: {pct_b:.1%}"


def test_get_variante_isolada_por_experimento():
    """Mesmo UID em experimentos diferentes é tratado de forma independente."""
    from app.services.ab_service import get_variante

    v1 = get_variante("uid-abc", "AB-001")
    v2 = get_variante("uid-abc", "AB-002")
    assert v1 in ("A", "B")
    assert v2 in ("A", "B")


def test_get_variante_split_customizado():
    """split=1.0 força todos para 'B'; split=0.0 força todos para 'A'."""
    from app.services.ab_service import get_variante

    for i in range(20):
        assert get_variante(f"uid-{i}", "AB-001", split=1.0) == "B"
        assert get_variante(f"uid-{i}", "AB-001", split=0.0) == "A"
