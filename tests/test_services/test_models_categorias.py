"""
Testes de CategoriaSetor, CategoriaGate, CategoriaImpacto (Fase 2 — Postgres real).

Substitui a suíte anterior baseada em mock do Firestore: aqui o comportamento é
validado contra um banco Postgres de teste real (fixture db_session), não o
formato da chamada a um driver específico.
"""

from unittest.mock import patch

import pytest

pytestmark = pytest.mark.usefixtures("db_session")


def _traduzir_mock():
    return {"en": "Test EN", "es": "Test ES"}


# ── CategoriaSetor ─────────────────────────────────────────────────────────────


def test_setor_from_dict_cria_com_campos_corretos():
    """CategoriaSetor.from_dict cria objeto com campos corretos (sem tocar o banco)."""
    from app.models_categorias import CategoriaSetor

    with patch("app.models_categorias.traduzir_categoria", return_value={"en": "Eng", "es": "Ing"}):
        s = CategoriaSetor.from_dict(
            {
                "nome_pt": "Engenharia",
                "nome_en": "Engineering",
                "nome_es": "Ingeniería",
                "ativo": True,
            },
            id=42,
        )

    assert s.id == 42
    assert s.nome_pt == "Engenharia"
    assert s.nome_en == "Engineering"
    assert s.ativo is True


def test_setor_to_dict_contem_campos_esperados():
    """CategoriaSetor.to_dict retorna dict com todos os campos."""
    from app.models_categorias import CategoriaSetor

    with patch(
        "app.models_categorias.traduzir_categoria", return_value={"en": "Maint", "es": "Mant"}
    ):
        s = CategoriaSetor(nome_pt="Manutencao", nome_en="Maintenance", nome_es="Mantenimiento")
        d = s.to_dict()

    assert d["nome_pt"] == "Manutencao"
    assert d["nome_en"] == "Maintenance"
    assert "ativo" in d
    assert "data_criacao" in d


def test_setor_save_novo_persiste_e_retorna_id(app):
    """CategoriaSetor.save() sem id insere linha nova e retorna o id gerado."""
    from app.models_categorias import CategoriaSetor

    with patch("app.models_categorias.traduzir_categoria", return_value={"en": "New", "es": "Nue"}):
        s = CategoriaSetor(nome_pt="Novo Setor", nome_en="New", nome_es="Nuevo")
        result = s.save()

    assert result is not None
    assert s.id == result

    recarregado = CategoriaSetor.get_by_id(result)
    assert recarregado is not None
    assert recarregado.nome_pt == "Novo Setor"


def test_setor_save_existente_atualiza_linha(app):
    """CategoriaSetor.save() com id já persistido atualiza a linha existente."""
    from app.models_categorias import CategoriaSetor

    with patch("app.models_categorias.traduzir_categoria", return_value={"en": "E", "es": "E"}):
        s = CategoriaSetor(nome_pt="Original", nome_en="Original", nome_es="Original")
        setor_id = s.save()

        s.nome_pt = "Renomeado"
        s.save()

    recarregado = CategoriaSetor.get_by_id(setor_id)
    assert recarregado.nome_pt == "Renomeado"


def test_setor_get_all_retorna_so_ativos(app):
    """CategoriaSetor.get_all() retorna só setores com ativo=True."""
    from app.models_categorias import CategoriaSetor

    with patch("app.models_categorias.traduzir_categoria", return_value={"en": "X", "es": "X"}):
        ativo = CategoriaSetor(nome_pt="Ativo", nome_en="A", nome_es="A", ativo=True)
        ativo.save()
        inativo = CategoriaSetor(nome_pt="Inativo", nome_en="I", nome_es="I", ativo=False)
        inativo.save()

    result = CategoriaSetor.get_all()

    nomes = {r.nome_pt for r in result}
    assert "Ativo" in nomes
    assert "Inativo" not in nomes


def test_setor_get_all_incluindo_inativos_retorna_ambos(app):
    """get_all_incluindo_inativos retorna setores ativos e inativos."""
    from app.models_categorias import CategoriaSetor

    with patch("app.models_categorias.traduzir_categoria", return_value={"en": "X", "es": "X"}):
        CategoriaSetor(nome_pt="Ativo2", nome_en="A", nome_es="A", ativo=True).save()
        CategoriaSetor(nome_pt="Inativo2", nome_en="I", nome_es="I", ativo=False).save()

    result = CategoriaSetor.get_all_incluindo_inativos()

    nomes = {r.nome_pt for r in result}
    assert "Ativo2" in nomes
    assert "Inativo2" in nomes


def test_setor_get_by_id_nao_encontrado_retorna_none(app):
    """CategoriaSetor.get_by_id retorna None para id inexistente."""
    from app.models_categorias import CategoriaSetor

    assert CategoriaSetor.get_by_id(999999) is None


def test_setor_get_by_id_id_invalido_retorna_none(app):
    """CategoriaSetor.get_by_id retorna None (não lança) para id malformado."""
    from app.models_categorias import CategoriaSetor

    assert CategoriaSetor.get_by_id("nao-e-um-numero") is None


def test_setor_nome_existe_vazio_retorna_false(app):
    from app.models_categorias import CategoriaSetor

    assert CategoriaSetor.nome_existe("   ") is False


def test_setor_nome_existe_encontrado_case_insensitive(app):
    """nome_existe compara case-insensitive e ignora espaços nas pontas."""
    from app.models_categorias import CategoriaSetor

    with patch("app.models_categorias.traduzir_categoria", return_value={"en": "M", "es": "M"}):
        CategoriaSetor(nome_pt="Manutenção", nome_en="M", nome_es="M").save()

    assert CategoriaSetor.nome_existe("  manutenção  ") is True


def test_setor_nome_existe_ignora_id_atual(app):
    """nome_existe não considera duplicidade contra o próprio registro sendo editado."""
    from app.models_categorias import CategoriaSetor

    with patch("app.models_categorias.traduzir_categoria", return_value={"en": "M", "es": "M"}):
        setor_id = CategoriaSetor(nome_pt="Qualidade", nome_en="Q", nome_es="Q").save()

    assert CategoriaSetor.nome_existe("Qualidade", id_atual=setor_id) is False


def test_setor_nome_existe_nao_encontrado_retorna_false(app):
    from app.models_categorias import CategoriaSetor

    assert CategoriaSetor.nome_existe("Nome Que Nao Existe Em Lugar Nenhum") is False


def test_setor_delete_remove_linha(app):
    """CategoriaSetor.delete() remove a linha e retorna True."""
    from app.models_categorias import CategoriaSetor

    with patch("app.models_categorias.traduzir_categoria", return_value={"en": "D", "es": "D"}):
        s = CategoriaSetor(nome_pt="Pra Deletar", nome_en="D", nome_es="D")
        setor_id = s.save()

    assert s.delete() is True
    assert CategoriaSetor.get_by_id(setor_id) is None


def test_setor_delete_sem_id_nao_lanca(app):
    """CategoriaSetor.delete() sem persistir antes não lança, retorna True (idempotente)."""
    from app.models_categorias import CategoriaSetor

    with patch("app.models_categorias.traduzir_categoria", return_value={"en": "D", "es": "D"}):
        s = CategoriaSetor(nome_pt="Nunca Salvo", nome_en="D", nome_es="D")

    assert s.delete() is True


# ── CategoriaGate ─────────────────────────────────────────────────────────────


def test_gate_from_dict_carrega_gate_pai_e_etapa():
    from app.models_categorias import CategoriaGate

    with patch("app.models_categorias.traduzir_categoria", return_value={"en": "G", "es": "G"}):
        g = CategoriaGate.from_dict(
            {
                "nome_pt": "Gate 1 - Desmontagem",
                "gate_pai": "Gate 1",
                "etapa": "Desmontagem",
                "ordem": 1,
                "ativo": True,
            },
            id=7,
        )

    assert g.id == 7
    assert g.gate_pai == "Gate 1"
    assert g.etapa == "Desmontagem"
    assert g.nome_pt == "Gate 1 - Desmontagem"


def test_gate_to_dict_inclui_gate_pai_e_etapa():
    from app.models_categorias import CategoriaGate

    with patch("app.models_categorias.traduzir_categoria", return_value={"en": "G", "es": "G"}):
        g = CategoriaGate(nome_pt="Gate 2 - Forno", gate_pai="Gate 2", etapa="Forno")
        d = g.to_dict()

    assert d["gate_pai"] == "Gate 2"
    assert d["etapa"] == "Forno"


def test_gate_save_novo_persiste(app):
    from app.models_categorias import CategoriaGate

    with patch("app.models_categorias.traduzir_categoria", return_value={"en": "G", "es": "G"}):
        g = CategoriaGate(nome_pt="Gate Novo", gate_pai="Gate X", etapa="Y", ordem=1)
        result = g.save()

    assert result is not None
    assert CategoriaGate.get_by_id(result).nome_pt == "Gate Novo"


def test_gate_get_all_retorna_ordenado_por_gate_pai_e_ordem(app):
    """CategoriaGate.get_all() ordena por (gate_pai, ordem)."""
    from app.models_categorias import CategoriaGate

    with patch("app.models_categorias.traduzir_categoria", return_value={"en": "G", "es": "G"}):
        CategoriaGate(nome_pt="Gate 1 - B", gate_pai="Gate 1", etapa="B", ordem=2).save()
        CategoriaGate(nome_pt="Gate 1 - A", gate_pai="Gate 1", etapa="A", ordem=1).save()

    result = CategoriaGate.get_all()
    ordens = [g.ordem for g in result if g.gate_pai == "Gate 1"]
    assert ordens == sorted(ordens)


def test_gate_get_all_ativos_retorna_so_ativos(app):
    from app.models_categorias import CategoriaGate

    with patch("app.models_categorias.traduzir_categoria", return_value={"en": "G", "es": "G"}):
        CategoriaGate(nome_pt="Gate Ativo", gate_pai="G", etapa="At", ativo=True).save()
        CategoriaGate(nome_pt="Gate Inativo", gate_pai="G", etapa="In", ativo=False).save()

    result = CategoriaGate.get_all_ativos()
    nomes = {g.nome_pt for g in result}
    assert "Gate Ativo" in nomes
    assert "Gate Inativo" not in nomes


def test_gate_get_by_id_nao_encontrado_retorna_none(app):
    from app.models_categorias import CategoriaGate

    assert CategoriaGate.get_by_id(999999) is None


def test_gate_nome_existe_encontrado(app):
    from app.models_categorias import CategoriaGate

    with patch("app.models_categorias.traduzir_categoria", return_value={"en": "G", "es": "G"}):
        CategoriaGate(nome_pt="Gate 1 - Desmontagem", gate_pai="Gate 1", etapa="Desmontagem").save()

    assert CategoriaGate.nome_existe("Gate 1 - Desmontagem") is True
    assert CategoriaGate.nome_existe("Gate 2 - Montagem") is False


def test_gate_delete_remove_linha(app):
    from app.models_categorias import CategoriaGate

    with patch("app.models_categorias.traduzir_categoria", return_value={"en": "G", "es": "G"}):
        g = CategoriaGate(nome_pt="Gate Deletar", gate_pai="G", etapa="D")
        gate_id = g.save()

    assert g.delete() is True
    assert CategoriaGate.get_by_id(gate_id) is None


# ── CategoriaImpacto ──────────────────────────────────────────────────────────


def test_impacto_from_dict_cria_com_campos_corretos():
    from app.models_categorias import CategoriaImpacto

    with patch(
        "app.models_categorias.traduzir_categoria", return_value={"en": "High", "es": "Alto"}
    ):
        imp = CategoriaImpacto.from_dict(
            {"nome_pt": "Alto", "nivel": 3, "cor": "#red"},
            id=5,
        )

    assert imp.id == 5
    assert imp.nivel == 3
    assert imp.cor == "#red"


def test_impacto_save_novo_persiste(app):
    from app.models_categorias import CategoriaImpacto

    with patch("app.models_categorias.traduzir_categoria", return_value={"en": "H", "es": "H"}):
        imp = CategoriaImpacto(nome_pt="Novo Impacto", nivel=2, cor="orange")
        result = imp.save()

    assert result is not None
    recarregado = CategoriaImpacto.get_by_id(result)
    assert recarregado.nivel == 2
    assert recarregado.cor == "orange"


def test_impacto_get_all_retorna_so_ativos(app):
    from app.models_categorias import CategoriaImpacto

    with patch("app.models_categorias.traduzir_categoria", return_value={"en": "H", "es": "H"}):
        CategoriaImpacto(nome_pt="Impacto Ativo", ativo=True).save()
        CategoriaImpacto(nome_pt="Impacto Inativo", ativo=False).save()

    result = CategoriaImpacto.get_all()
    nomes = {r.nome_pt for r in result}
    assert "Impacto Ativo" in nomes
    assert "Impacto Inativo" not in nomes


def test_impacto_get_all_incluindo_inativos_retorna_ambos(app):
    from app.models_categorias import CategoriaImpacto

    with patch("app.models_categorias.traduzir_categoria", return_value={"en": "H", "es": "H"}):
        CategoriaImpacto(nome_pt="Impacto Ativo2", ativo=True).save()
        CategoriaImpacto(nome_pt="Impacto Inativo2", ativo=False).save()

    result = CategoriaImpacto.get_all_incluindo_inativos()
    nomes = {r.nome_pt for r in result}
    assert "Impacto Ativo2" in nomes
    assert "Impacto Inativo2" in nomes


def test_impacto_get_by_id_nao_encontrado_retorna_none(app):
    from app.models_categorias import CategoriaImpacto

    assert CategoriaImpacto.get_by_id(999999) is None


def test_impacto_nome_existe_encontrado(app):
    from app.models_categorias import CategoriaImpacto

    with patch("app.models_categorias.traduzir_categoria", return_value={"en": "H", "es": "H"}):
        CategoriaImpacto(nome_pt="Crítico").save()

    assert CategoriaImpacto.nome_existe("crítico") is True
    assert CategoriaImpacto.nome_existe(None) is False


def test_impacto_delete_remove_linha(app):
    from app.models_categorias import CategoriaImpacto

    with patch("app.models_categorias.traduzir_categoria", return_value={"en": "H", "es": "H"}):
        imp = CategoriaImpacto(nome_pt="Impacto Deletar")
        impacto_id = imp.save()

    assert imp.delete() is True
    assert CategoriaImpacto.get_by_id(impacto_id) is None
