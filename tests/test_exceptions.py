"""Testes das exceções customizadas (ChamadoNaoEncontradoError, ValidacaoChamadoError) e de fluxos que as levantam."""
import pytest

from app.exceptions import (
    ChamadoError,
    ChamadoNaoEncontradoError,
    ValidacaoChamadoError,
)
from app.models import Chamado


class TestChamadoNaoEncontradoError:
    """Cobertura de ChamadoNaoEncontradoError."""

    def test_herda_de_chamado_error(self):
        assert issubclass(ChamadoNaoEncontradoError, ChamadoError)

    def test_mensagem_contem_chamado_id(self):
        exc = ChamadoNaoEncontradoError('ch_123')
        assert 'ch_123' in str(exc)
        assert 'não encontrado' in str(exc).lower()

    def test_atributo_chamado_id(self):
        exc = ChamadoNaoEncontradoError('doc_xyz')
        assert exc.chamado_id == 'doc_xyz'


class TestValidacaoChamadoError:
    """Cobertura de ValidacaoChamadoError."""

    def test_herda_de_chamado_error(self):
        assert issubclass(ValidacaoChamadoError, ChamadoError)

    def test_mensagem_e_atributos(self):
        exc = ValidacaoChamadoError('Descrição obrigatória', erros=['campo descricao'])
        assert exc.mensagem == 'Descrição obrigatória'
        assert exc.erros == ['campo descricao']
        assert 'Descrição obrigatória' in str(exc)

    def test_erros_opcional_padrao_lista_vazia(self):
        exc = ValidacaoChamadoError('Dados inválidos')
        assert exc.erros == []
        assert exc.mensagem == 'Dados inválidos'


class TestChamadoFromDictLevantaValidacaoChamadoError:
    """Chamado.from_dict() levanta ValidacaoChamadoError em edge cases."""

    def test_dados_vazios_levanta_validacao_chamado_error(self):
        with pytest.raises(ValidacaoChamadoError) as exc_info:
            Chamado.from_dict({})
        assert 'vazios' in str(exc_info.value).lower() or 'vazio' in str(exc_info.value).lower()
        assert exc_info.value.mensagem

    def test_dados_none_levanta_validacao_chamado_error(self):
        with pytest.raises(ValidacaoChamadoError) as exc_info:
            Chamado.from_dict(None)
        assert exc_info.value.mensagem
