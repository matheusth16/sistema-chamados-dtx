"""Testes das exceções customizadas e de fluxos que as levantam."""

import pytest

from app.exceptions import (
    ArquivoNaoPermitidoError,
    AutenticacaoError,
    ChamadoError,
    ChamadoNaoEncontradoError,
    DocumentoNaoEncontradoError,
    ErroTransacaoError,
    FirestoreError,
    PermissaoNegadaError,
    TamanhoArquivoExcedidoError,
    UploadError,
    UsuarioError,
    UsuarioNaoEncontradoError,
    ValidacaoChamadoError,
)
from app.models import Chamado


class TestChamadoNaoEncontradoError:
    """Cobertura de ChamadoNaoEncontradoError."""

    def test_herda_de_chamado_error(self):
        assert issubclass(ChamadoNaoEncontradoError, ChamadoError)

    def test_mensagem_contem_chamado_id(self):
        exc = ChamadoNaoEncontradoError("ch_123")
        assert "ch_123" in str(exc)
        assert "não encontrado" in str(exc).lower()

    def test_atributo_chamado_id(self):
        exc = ChamadoNaoEncontradoError("doc_xyz")
        assert exc.chamado_id == "doc_xyz"


class TestValidacaoChamadoError:
    """Cobertura de ValidacaoChamadoError."""

    def test_herda_de_chamado_error(self):
        assert issubclass(ValidacaoChamadoError, ChamadoError)

    def test_mensagem_e_atributos(self):
        exc = ValidacaoChamadoError("Descrição obrigatória", erros=["campo descricao"])
        assert exc.mensagem == "Descrição obrigatória"
        assert exc.erros == ["campo descricao"]
        assert "Descrição obrigatória" in str(exc)

    def test_erros_opcional_padrao_lista_vazia(self):
        exc = ValidacaoChamadoError("Dados inválidos")
        assert exc.erros == []
        assert exc.mensagem == "Dados inválidos"


class TestUsuarioNaoEncontradoError:
    def test_herda_de_usuario_error(self):
        assert issubclass(UsuarioNaoEncontradoError, UsuarioError)

    def test_atributo_email(self):
        exc = UsuarioNaoEncontradoError("user@test.com")
        assert exc.email == "user@test.com"

    def test_mensagem_contem_email(self):
        exc = UsuarioNaoEncontradoError("user@test.com")
        assert "user@test.com" in str(exc)
        assert "não encontrado" in str(exc).lower()


class TestAutenticacaoError:
    def test_herda_de_usuario_error(self):
        assert issubclass(AutenticacaoError, UsuarioError)

    def test_mensagem_padrao(self):
        exc = AutenticacaoError()
        assert "Email" in str(exc) or "senha" in str(exc).lower()

    def test_mensagem_customizada(self):
        exc = AutenticacaoError("Sessão expirada")
        assert "Sessão expirada" in str(exc)


class TestPermissaoNegadaError:
    def test_herda_de_usuario_error(self):
        assert issubclass(PermissaoNegadaError, UsuarioError)

    def test_mensagem_padrao(self):
        exc = PermissaoNegadaError()
        assert "permissão" in str(exc).lower()

    def test_mensagem_customizada(self):
        exc = PermissaoNegadaError("Apenas admins podem acessar")
        assert "Apenas admins" in str(exc)


class TestDocumentoNaoEncontradoError:
    def test_herda_de_firestore_error(self):
        assert issubclass(DocumentoNaoEncontradoError, FirestoreError)

    def test_atributos_colecao_e_doc_id(self):
        exc = DocumentoNaoEncontradoError("chamados", "abc123")
        assert exc.colecao == "chamados"
        assert exc.doc_id == "abc123"

    def test_mensagem_contem_colecao_e_doc_id(self):
        exc = DocumentoNaoEncontradoError("usuarios", "uid_xyz")
        assert "uid_xyz" in str(exc)
        assert "usuarios" in str(exc)


class TestErroTransacaoError:
    def test_herda_de_firestore_error(self):
        assert issubclass(ErroTransacaoError, FirestoreError)

    def test_mensagem_contem_prefixo_e_detalhe(self):
        exc = ErroTransacaoError("timeout na escrita")
        assert "Erro em transação Firestore" in str(exc)
        assert "timeout na escrita" in str(exc)


class TestArquivoNaoPermitidoError:
    def test_herda_de_upload_error(self):
        assert issubclass(ArquivoNaoPermitidoError, UploadError)

    def test_atributos_extensao_e_permitidas(self):
        exc = ArquivoNaoPermitidoError("exe", ["pdf", "xlsx"])
        assert exc.extensao == "exe"
        assert exc.permitidas == ["pdf", "xlsx"]

    def test_mensagem_lista_extensoes_permitidas(self):
        exc = ArquivoNaoPermitidoError("bat", ["pdf", "docx"])
        assert "bat" in str(exc)
        assert "pdf" in str(exc)
        assert "docx" in str(exc)


class TestTamanhoArquivoExcedidoError:
    def test_herda_de_upload_error(self):
        assert issubclass(TamanhoArquivoExcedidoError, UploadError)

    def test_atributos_tamanho_e_maximo(self):
        exc = TamanhoArquivoExcedidoError(15.5, 10.0)
        assert exc.tamanho_mb == 15.5
        assert exc.maximo_mb == 10.0

    def test_mensagem_contem_tamanhos(self):
        exc = TamanhoArquivoExcedidoError(12.34, 10.0)
        assert "12.34" in str(exc)
        assert "10.0" in str(exc)


class TestChamadoFromDictLevantaValidacaoChamadoError:
    """Chamado.from_dict() levanta ValidacaoChamadoError em edge cases."""

    def test_dados_vazios_levanta_validacao_chamado_error(self):
        with pytest.raises(ValidacaoChamadoError) as exc_info:
            Chamado.from_dict({})
        assert "vazios" in str(exc_info.value).lower() or "vazio" in str(exc_info.value).lower()
        assert exc_info.value.mensagem

    def test_dados_none_levanta_validacao_chamado_error(self):
        with pytest.raises(ValidacaoChamadoError) as exc_info:
            Chamado.from_dict(None)
        assert exc_info.value.mensagem
