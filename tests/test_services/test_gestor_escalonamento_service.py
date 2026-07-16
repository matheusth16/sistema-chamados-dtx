"""TDD: testes do serviço gestor_escalonamento_service — fonte única de verdade
para e-mails de escalonamento gerencial (nivel_gestao), sem configuração
paralela em variável de ambiente (GESTOR_EMAILS removida)."""

from unittest.mock import MagicMock, patch

import pytest

from app.services.gestor_escalonamento_service import (
    construir_mapa_gestor_setor,
    construir_mapa_niveis_superiores,
    resolver_email_gestor,
    resolver_email_gestor_com_cascata,
)


@pytest.fixture(autouse=True)
def _limpa_cache_gestores():
    from app.cache import static_cache_delete

    static_cache_delete("sla_gestores_usuarios")
    yield
    static_cache_delete("sla_gestores_usuarios")


def _make_usuario(email, nivel_gestao, areas=None, ativo=True):
    u = MagicMock()
    u.email = email
    u.nivel_gestao = nivel_gestao
    u.areas = areas or []
    u.ativo = ativo
    return u


# ---------------------------------------------------------------------------
# construir_mapa_niveis_superiores
# ---------------------------------------------------------------------------


def test_niveis_superiores_mapeia_cada_nivel_ao_seu_email():
    usuarios = [
        _make_usuario("producao@dtx.aero", "gerente_producao"),
        _make_usuario("assistente@dtx.aero", "assistente_gm"),
        _make_usuario("gm@dtx.aero", "gm"),
    ]
    with patch("app.models_usuario.Usuario.get_all", return_value=usuarios):
        mapa = construir_mapa_niveis_superiores()

    assert mapa == {
        "gerente_producao": "producao@dtx.aero",
        "assistente_gm": "assistente@dtx.aero",
        "gm": "gm@dtx.aero",
    }


def test_niveis_superiores_ignora_gestor_setor():
    """gestor_setor não é um dos níveis superiores — não deve aparecer no mapa company-wide."""
    usuarios = [_make_usuario("setor@dtx.aero", "gestor_setor", areas=["Manutencao"])]
    with patch("app.models_usuario.Usuario.get_all", return_value=usuarios):
        mapa = construir_mapa_niveis_superiores()

    assert mapa == {}


def test_niveis_superiores_ignora_usuario_sem_nivel_gestao():
    usuarios = [_make_usuario("supervisor@dtx.aero", None)]
    with patch("app.models_usuario.Usuario.get_all", return_value=usuarios):
        mapa = construir_mapa_niveis_superiores()

    assert mapa == {}


def test_niveis_superiores_ignora_usuario_inativo():
    usuarios = [_make_usuario("ex-gm@dtx.aero", "gm", ativo=False)]
    with patch("app.models_usuario.Usuario.get_all", return_value=usuarios):
        mapa = construir_mapa_niveis_superiores()

    assert mapa == {}


def test_niveis_superiores_ignora_usuario_sem_email():
    usuarios = [_make_usuario("", "gm")]
    with patch("app.models_usuario.Usuario.get_all", return_value=usuarios):
        mapa = construir_mapa_niveis_superiores()

    assert mapa == {}


def test_niveis_superiores_conflito_mantem_primeiro_alfabetico_e_loga_warning():
    """Duas pessoas com o mesmo nivel_gestao (ex.: dois GMs cadastrados): mantém a
    primeira em ordem alfabética e loga warning, não quebra o job."""
    usuarios = [
        _make_usuario("zeta@dtx.aero", "gm"),
        _make_usuario("alfa@dtx.aero", "gm"),
    ]
    with (
        patch("app.models_usuario.Usuario.get_all", return_value=usuarios),
        patch("app.services.gestor_escalonamento_service.logger") as mock_logger,
    ):
        mapa = construir_mapa_niveis_superiores()

    assert mapa == {"gm": "alfa@dtx.aero"}
    mock_logger.warning.assert_called_once()


def test_niveis_superiores_firestore_erro_retorna_vazio():
    with patch("app.models_usuario.Usuario.get_all", side_effect=Exception("boom")):
        mapa = construir_mapa_niveis_superiores()

    assert mapa == {}


def test_niveis_superiores_e_gestor_setor_compartilham_cache_usuario_get_all():
    """Construir os dois mapas no mesmo ciclo do job só deve ler Usuario.get_all 1 vez."""
    usuarios = [
        _make_usuario("setor@dtx.aero", "gestor_setor", areas=["Manutencao"]),
        _make_usuario("producao@dtx.aero", "gerente_producao"),
    ]
    with patch("app.models_usuario.Usuario.get_all", return_value=usuarios) as mock_get_all:
        construir_mapa_gestor_setor()
        construir_mapa_niveis_superiores()

    assert mock_get_all.call_count == 1


# ---------------------------------------------------------------------------
# resolver_email_gestor
# ---------------------------------------------------------------------------


def test_resolver_email_gestor_setor_usa_mapa_por_area():
    mapa_setor = {"Manutencao": "setor@dtx.aero"}
    assert resolver_email_gestor("gestor_setor", "Manutencao", mapa_setor, {}) == "setor@dtx.aero"


def test_resolver_email_gestor_setor_sem_area_mapeada_retorna_none():
    """Sem fallback flat: se a área do chamado não tem gestor_setor cadastrado, None."""
    mapa_setor = {"Qualidade": "qualidade@dtx.aero"}
    assert resolver_email_gestor("gestor_setor", "Manutencao", mapa_setor, {}) is None


def test_resolver_email_gestor_nivel_superior_usa_mapa_company_wide():
    mapa_superiores = {"gerente_producao": "producao@dtx.aero"}
    assert (
        resolver_email_gestor("gerente_producao", "QualquerArea", {}, mapa_superiores)
        == "producao@dtx.aero"
    )


def test_resolver_email_gestor_nivel_superior_sem_pessoa_cadastrada_retorna_none():
    assert resolver_email_gestor("gm", "QualquerArea", {}, {}) is None


def test_resolver_email_gestor_chave_none_retorna_none():
    """Nível > 4 (fora de NIVEL_PARA_CHAVE_GESTOR) não deve quebrar — retorna None."""
    assert resolver_email_gestor(None, "QualquerArea", {}, {}) is None


# ---------------------------------------------------------------------------
# resolver_email_gestor_com_cascata — usado no broadcast de AOG (emergência):
# nível sem ninguém cadastrado cai pro próximo nível de gestão acima, nunca
# fica sem notificar por lacuna de cadastro.
# ---------------------------------------------------------------------------


def test_cascata_nivel_presente_retorna_o_proprio_sem_cascatear():
    mapa_superiores = {"gerente_producao": "producao@dtx.aero", "gm": "gm@dtx.aero"}
    assert (
        resolver_email_gestor_com_cascata("gerente_producao", "Manutencao", {}, mapa_superiores)
        == "producao@dtx.aero"
    )


def test_cascata_nivel_ausente_sobe_para_o_proximo_nivel():
    """gerente_producao ausente, assistente_gm presente → cascateia pro assistente_gm."""
    mapa_superiores = {"assistente_gm": "assistente@dtx.aero"}
    assert (
        resolver_email_gestor_com_cascata("gerente_producao", "Manutencao", {}, mapa_superiores)
        == "assistente@dtx.aero"
    )


def test_cascata_pula_varios_niveis_ausentes_ate_achar_gm():
    """gerente_producao e assistente_gm ausentes, só gm cadastrado → cascateia até gm."""
    mapa_superiores = {"gm": "gm@dtx.aero"}
    assert (
        resolver_email_gestor_com_cascata("gerente_producao", "Manutencao", {}, mapa_superiores)
        == "gm@dtx.aero"
    )


def test_cascata_gestor_setor_ausente_cascateia_para_niveis_superiores():
    """gestor_setor sem ninguém cadastrado pra área → cascateia pra gerente_producao."""
    mapa_setor = {"Qualidade": "qualidade@dtx.aero"}  # não tem "Manutencao"
    mapa_superiores = {"gerente_producao": "producao@dtx.aero"}
    assert (
        resolver_email_gestor_com_cascata("gestor_setor", "Manutencao", mapa_setor, mapa_superiores)
        == "producao@dtx.aero"
    )


def test_cascata_gm_ausente_nao_tem_pra_onde_cascatear_retorna_none():
    """gm é o topo da cadeia — sem ninguém cadastrado, não há nível acima; retorna None."""
    assert resolver_email_gestor_com_cascata("gm", "Manutencao", {}, {}) is None


def test_cascata_nenhum_nivel_cadastrado_retorna_none():
    assert resolver_email_gestor_com_cascata("gestor_setor", "Manutencao", {}, {}) is None
