"""Testes do serviço de permissões: usuario_pode_ver_chamado e edge cases (supervisor de outra área)."""
import pytest
from unittest.mock import MagicMock

from app.services.permissions import usuario_pode_ver_chamado, usuario_pode_ver_chamado_otimizado


def _chamado_mock(area='Manutencao', responsavel_id='sup_1'):
    c = MagicMock()
    c.area = area
    c.responsavel_id = responsavel_id
    return c


def _usuario_mock(perfil, areas=None):
    u = MagicMock()
    u.perfil = perfil
    u.areas = areas or []
    return u


class TestUsuarioPodeVerChamado:
    """Cobertura de usuario_pode_ver_chamado."""

    def test_admin_pode_ver_qualquer_chamado(self):
        admin = _usuario_mock('admin', areas=[])
        chamado = _chamado_mock(area='TI')
        assert usuario_pode_ver_chamado(admin, chamado) is True
        chamado.area = 'QualquerArea'
        assert usuario_pode_ver_chamado(admin, chamado) is True

    def test_supervisor_pode_ver_chamado_da_sua_area(self):
        supervisor = _usuario_mock('supervisor', areas=['Manutencao', 'TI'])
        chamado = _chamado_mock(area='Manutencao')
        assert usuario_pode_ver_chamado(supervisor, chamado) is True
        chamado.area = 'TI'
        assert usuario_pode_ver_chamado(supervisor, chamado) is True

    def test_supervisor_nao_pode_ver_chamado_de_outra_area(self):
        """Edge case: supervisor de outra área não pode ver/editar chamado."""
        supervisor = _usuario_mock('supervisor', areas=['Manutencao'])
        chamado = _chamado_mock(area='TI')
        assert usuario_pode_ver_chamado(supervisor, chamado) is False
        chamado.area = 'Planejamento'
        assert usuario_pode_ver_chamado(supervisor, chamado) is False

    def test_supervisor_area_unica_chamado_outra_retorna_false(self):
        """Supervisor com uma única área não vê chamados de outras áreas."""
        supervisor = _usuario_mock('supervisor', areas=['Engenharia'])
        chamado = _chamado_mock(area='RH')
        assert usuario_pode_ver_chamado(supervisor, chamado) is False

    def test_solicitante_nao_pode_ver_por_perfil(self):
        """Solicitante não tem permissão (regra de negócio: só supervisor/admin)."""
        solicitante = _usuario_mock('solicitante', areas=['Manutencao'])
        chamado = _chamado_mock(area='Manutencao')
        assert usuario_pode_ver_chamado(solicitante, chamado) is False

    def test_supervisor_areas_vazias_nao_pode_ver_nenhum_chamado(self):
        supervisor = _usuario_mock('supervisor', areas=[])
        chamado = _chamado_mock(area='Manutencao')
        assert usuario_pode_ver_chamado(supervisor, chamado) is False


class TestUsuarioPodeVerChamadoOtimizado:
    """Cobertura da versão otimizada (mesma regra por área)."""

    def test_supervisor_outra_area_retorna_false(self):
        supervisor = _usuario_mock('supervisor', areas=['AreaA'])
        chamado = _chamado_mock(area='AreaB')
        assert usuario_pode_ver_chamado_otimizado(supervisor, chamado) is False

    def test_supervisor_mesma_area_retorna_true(self):
        supervisor = _usuario_mock('supervisor', areas=['AreaA'])
        chamado = _chamado_mock(area='AreaA')
        assert usuario_pode_ver_chamado_otimizado(supervisor, chamado) is True

    def test_admin_retorna_true_ignora_cache(self):
        admin = _usuario_mock('admin', areas=[])
        chamado = _chamado_mock(area='Qualquer')
        assert usuario_pode_ver_chamado_otimizado(admin, chamado, cache_usuarios={}) is True
