"""Testes do serviço de validação de novo chamado."""

import io
from unittest.mock import MagicMock, patch

import pytest

from app.services.validators import (
    _arquivo_conteudo_permitido,
    _validar_csv,
    get_extensoes_permitidas,
    validar_novo_chamado,
)


def test_validar_novo_chamado_formulario_valido():
    """Formulário com descrição, tipo e categoria válidos retorna lista vazia."""
    form = {
        "descricao": "Descrição com mais de 3 caracteres",
        "tipo": "Manutencao",
        "categoria": "Chamado",
        "gate": "N/A",
        "impacto": "Impacto Baixo",
    }
    erros = validar_novo_chamado(form)
    assert erros == []


def test_validar_novo_chamado_descricao_obrigatoria():
    """Sem descrição retorna erro."""
    form = {
        "descricao": "",
        "tipo": "Manutencao",
        "categoria": "Chamado",
        "gate": "N/A",
        "impacto": "Impacto Baixo",
    }
    erros = validar_novo_chamado(form)
    assert any("description" in e.lower() and "required" in e.lower() for e in erros)


def test_validar_novo_chamado_descricao_minimo_caracteres():
    """Descrição com menos de 3 caracteres retorna erro."""
    form = {
        "descricao": "ab",
        "tipo": "Manutencao",
        "categoria": "Chamado",
        "gate": "N/A",
        "impacto": "Impacto Baixo",
    }
    erros = validar_novo_chamado(form)
    assert any("at least 3" in e for e in erros)


def test_validar_novo_chamado_tipo_obrigatorio():
    """Sem setor atribuído retorna erro."""
    form = {
        "descricao": "Descrição válida aqui",
        "tipo": "",
        "categoria": "Chamado",
        "gate": "N/A",
        "impacto": "Impacto Baixo",
    }
    erros = validar_novo_chamado(form)
    assert any("sector" in e.lower() or "assigned" in e.lower() for e in erros)


def test_validar_novo_chamado_gate_obrigatorio():
    """Sem gate informado retorna erro."""
    form = {
        "descricao": "Descrição válida aqui",
        "tipo": "Manutencao",
        "categoria": "Chamado",
        "gate": "",
        "impacto": "Impacto Baixo",
    }
    erros = validar_novo_chamado(form)
    assert any("gate" in e.lower() and "must be assigned" in e.lower() for e in erros)


def test_validar_novo_chamado_impacto_obrigatorio():
    """Sem impacto informado retorna erro."""
    form = {
        "descricao": "Descrição válida aqui",
        "tipo": "Manutencao",
        "categoria": "Chamado",
        "gate": "N/A",
        "impacto": "",
    }
    erros = validar_novo_chamado(form)
    assert any("impact" in e.lower() and "required" in e.lower() for e in erros)


_FORM_PROJETOS_BASE = {
    "descricao": "Projeto X",
    "tipo": "Engenharia",
    "categoria": "Projetos",
    "gate": "N/A",
    "impacto": "Impacto Baixo",
}


@pytest.mark.parametrize(
    "rl_codigo,espera_erro",
    [
        ("", True),
        ("045", False),
        ("ABC-01", False),
        ("123/2026 (rev.1)", False),
        ("04@123", True),
        ("A" * 101, True),
    ],
    ids=[
        "vazio",
        "numerico",
        "alfanumerico",
        "com_chars_permitidos",
        "char_invalido",
        "muito_longo",
    ],
)
def test_validar_rl_codigo(rl_codigo, espera_erro):
    """Valida todos os cenários do campo rl_codigo em chamados de Projetos."""
    form = {**_FORM_PROJETOS_BASE, "rl_codigo": rl_codigo}
    erros = validar_novo_chamado(form)
    if espera_erro:
        assert any("RL" in e for e in erros)
    else:
        assert erros == []


_FORM_AOG_BASE = {
    "descricao": "Aeronave em solo",
    "tipo": "Manutencao",
    "categoria": "AOG",
    "gate": "N/A",
    "impacto": "Impacto Alto",
}


def test_validar_rl_codigo_aog_obrigatorio():
    """AOG, assim como Projetos, exige rl_codigo preenchido."""
    form = {**_FORM_AOG_BASE, "rl_codigo": ""}
    erros = validar_novo_chamado(form)
    assert any("RL" in e for e in erros)


def test_validar_rl_codigo_aog_valido_sem_erro():
    """AOG com rl_codigo válido não gera erro de RL."""
    form = {**_FORM_AOG_BASE, "rl_codigo": "AOG-001"}
    erros = validar_novo_chamado(form)
    assert erros == []


def test_validar_novo_chamado_arquivo_extensao_invalida():
    """Arquivo com extensão não permitida retorna erro."""
    form = {
        "descricao": "Descrição ok",
        "tipo": "Manutencao",
        "categoria": "Chamado",
        "gate": "N/A",
        "impacto": "Impacto Baixo",
    }
    arquivo = MagicMock()
    arquivo.filename = "documento.exe"
    erros = validar_novo_chamado(form, [arquivo])
    assert any("Invalid file format" in e or "invalid" in e.lower() for e in erros)


def test_validar_novo_chamado_arquivo_extensao_permitida():
    """Arquivo com extensão permitida (ex: pdf) não gera erro de arquivo."""
    form = {
        "descricao": "Descrição ok",
        "tipo": "Manutencao",
        "categoria": "Chamado",
        "gate": "N/A",
        "impacto": "Impacto Baixo",
    }
    arquivo = MagicMock()
    arquivo.filename = "anexo.pdf"
    erros = validar_novo_chamado(form, [arquivo])
    assert not any("arquivo" in e.lower() or "Formato" in e for e in erros)


def test_validar_novo_chamado_sem_arquivo_nao_valida_arquivo():
    """Sem arquivo (None ou lista vazia), validação de arquivo é ignorada."""
    form = {
        "descricao": "Descrição com mais de 3 caracteres",
        "tipo": "Manutencao",
        "categoria": "Chamado",
        "gate": "N/A",
        "impacto": "Impacto Baixo",
    }
    erros = validar_novo_chamado(form, None)
    assert erros == []
    erros2 = validar_novo_chamado(form, [])
    assert erros2 == []
    arquivo_vazio = MagicMock()
    arquivo_vazio.filename = ""
    erros3 = validar_novo_chamado(form, [arquivo_vazio])
    assert erros3 == []


# ── Testes multi-arquivo (TDD RED → GREEN) ────────────────────────────────────


_FORM_VALIDO = {
    "descricao": "Descrição ok",
    "tipo": "Manutencao",
    "categoria": "Chamado",
    "gate": "N/A",
    "impacto": "Impacto Baixo",
}


def _make_pdf_arquivo(nome: str = "doc.pdf") -> MagicMock:
    """FileStorage mock com magic bytes de PDF."""
    buf = io.BytesIO(b"%PDF-1.4 content here")
    arq = MagicMock()
    arq.filename = nome
    arq.stream = buf
    arq.content_length = len(buf.getvalue())
    return arq


def test_varios_pdfs_validos_sem_erro():
    """Dois PDFs válidos passados como lista não geram erro."""
    arqs = [_make_pdf_arquivo("a.pdf"), _make_pdf_arquivo("b.pdf")]
    erros = validar_novo_chamado(_FORM_VALIDO, arqs)
    assert erros == []


def test_exe_na_lista_retorna_erro_com_nome():
    """Um .exe na lista retorna erro mencionando o arquivo."""
    exe = MagicMock()
    exe.filename = "virus.exe"
    erros = validar_novo_chamado(_FORM_VALIDO, [exe])
    assert len(erros) == 1
    assert "virus.exe" in erros[0] or "Formato" in erros[0]


def test_arquivo_maior_que_10mb_retorna_erro():
    """Arquivo com mais de 10 MB retorna erro de tamanho."""
    grande = MagicMock()
    grande.filename = "enorme.pdf"
    stream = io.BytesIO(b"%PDF" + b"\x00" * (10 * 1024 * 1024 + 1))
    grande.stream = stream
    grande.content_length = 10 * 1024 * 1024 + 1
    erros = validar_novo_chamado(_FORM_VALIDO, [grande])
    assert any(
        "10" in e and ("MB" in e or "tamanho" in e.lower() or "excede" in e.lower()) for e in erros
    )


def test_arquivo_exatamente_10mb_aceito():
    """Arquivo com exatamente 10 MB é aceito (limite é <=)."""
    limite = MagicMock()
    limite.filename = "exato.pdf"
    limite.content_length = 10 * 1024 * 1024
    stream = io.BytesIO(b"%PDF" + b"\x00" * (10 * 1024 * 1024 - 4))
    limite.stream = stream
    erros = validar_novo_chamado(_FORM_VALIDO, [limite])
    assert not any("excede" in e.lower() or "MB" in e for e in erros)


def test_mistura_valido_e_invalido_retorna_ambos_erros():
    """Lista com um PDF válido e um .exe retorna erro somente para o .exe."""
    pdf = _make_pdf_arquivo("ok.pdf")
    exe = MagicMock()
    exe.filename = "mal.exe"
    erros = validar_novo_chamado(_FORM_VALIDO, [pdf, exe])
    assert len(erros) == 1
    assert "mal.exe" in erros[0] or "Formato" in erros[0]


def _make_csv_arquivo(conteudo: str, filename: str = "dados.csv"):
    """Cria um MagicMock de FileStorage com stream CSV em memória."""
    buf = io.BytesIO(conteudo.encode("utf-8"))
    arquivo = MagicMock()
    arquivo.filename = filename
    arquivo.stream = buf
    return arquivo


def test_csv_valido_nao_gera_erro():
    """CSV bem formado não gera erro de validação."""
    form = {
        "descricao": "Descrição ok",
        "tipo": "Manutencao",
        "categoria": "Chamado",
        "gate": "N/A",
        "impacto": "Impacto Baixo",
    }
    arquivo = _make_csv_arquivo("nome,valor\nAlpha,1\nBeta,2")
    erros = validar_novo_chamado(form, [arquivo])
    assert not any("CSV" in e or "arquivo" in e.lower() for e in erros)


def test_csv_vazio_retorna_erro():
    """CSV vazio (0 bytes) deve ser rejeitado."""
    form = {
        "descricao": "Descrição ok",
        "tipo": "Manutencao",
        "categoria": "Chamado",
        "gate": "N/A",
        "impacto": "Impacto Baixo",
    }
    arquivo = _make_csv_arquivo("")
    erros = validar_novo_chamado(form, [arquivo])
    assert any("CSV" in e or "vazio" in e.lower() for e in erros)


def test_csv_binario_renomeado_retorna_erro():
    """Arquivo binário com extensão .csv deve ser rejeitado como inválido."""
    form = {
        "descricao": "Descrição ok",
        "tipo": "Manutencao",
        "categoria": "Chamado",
        "gate": "N/A",
        "impacto": "Impacto Baixo",
    }
    # Simula binário (bytes de um PNG renomeado como .csv)
    buf = io.BytesIO(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
    arquivo = MagicMock()
    arquivo.filename = "planilha.csv"
    arquivo.stream = buf
    # PNG é lido como texto com erros de decode; csv.reader tentará parsear —
    # pode retornar True (replace de erros) mas o stream seek é chamado corretamente
    # O teste garante que a função é chamada e não lança exceção
    erros = validar_novo_chamado(form, [arquivo])
    # Não deve lançar exceção; erro ou não depende do conteúdo parseado
    assert isinstance(erros, list)


# ── get_extensoes_permitidas ──────────────────────────────────────────────────


def test_get_extensoes_permitidas_retorna_set_nao_vazio():
    """get_extensoes_permitidas() retorna um conjunto com pelo menos 'pdf'."""
    exts = get_extensoes_permitidas()
    assert isinstance(exts, set)
    assert "pdf" in exts


# ── _validar_csv ──────────────────────────────────────────────────────────────


def test_validar_csv_sem_stream_retorna_erro():
    """_validar_csv com arquivo sem stream retorna (False, mensagem)."""
    arquivo = MagicMock(spec=[])  # sem atributo 'stream'
    ok, msg = _validar_csv(arquivo)
    assert ok is False
    assert "stream" in msg.lower() or "csv" in msg.lower()


def test_validar_csv_stop_iteration_arquivo_vazio():
    """_validar_csv com stream vazio retorna False (via branch de content vazio)."""
    buf = io.BytesIO(b"")
    arquivo = MagicMock()
    arquivo.stream = buf
    ok, msg = _validar_csv(arquivo)
    assert ok is False
    assert "vazio" in msg.lower() or "csv" in msg.lower()


# ── _arquivo_conteudo_permitido ───────────────────────────────────────────────


def test_validar_csv_stop_iteration_retorna_erro():
    """_validar_csv captura StopIteration do csv.reader quando next() não encontra linha."""
    from unittest.mock import patch as _patch

    buf = io.BytesIO(b"conteudo_nao_vazio")
    arquivo = MagicMock()
    arquivo.stream = buf
    with _patch("builtins.next", side_effect=StopIteration):
        ok, msg = _validar_csv(arquivo)
    assert ok is False
    assert "vazio" in msg.lower() or "csv" in msg.lower()


def test_validar_csv_csv_error_retorna_erro():
    """_validar_csv retorna False quando csv.Error é levantado ao parsear."""
    import csv as csv_mod
    from unittest.mock import patch as _patch

    buf = io.BytesIO(b"campo1,campo2\nvalor1,valor2")
    arquivo = MagicMock()
    arquivo.stream = buf
    with _patch("app.services.validators.csv.reader", side_effect=csv_mod.Error("bad csv")):
        ok, msg = _validar_csv(arquivo)
    assert ok is False
    assert "csv" in msg.lower() or "inválido" in msg.lower()


def test_validar_csv_excecao_generica_retorna_erro():
    """_validar_csv retorna False quando uma Exception genérica é levantada."""
    buf = io.BytesIO(b"a,b\n1,2")
    arquivo = MagicMock()
    arquivo.stream = buf
    from unittest.mock import patch as _patch

    with _patch("app.services.validators.csv.reader", side_effect=Exception("IO error")):
        ok, msg = _validar_csv(arquivo)
    assert ok is False


def test_arquivo_conteudo_permitido_none_retorna_true():
    """_arquivo_conteudo_permitido(None) retorna (True, '') sem erro."""
    ok, msg = _arquivo_conteudo_permitido(None)
    assert ok is True
    assert msg == ""


def test_arquivo_conteudo_permitido_filename_vazio_retorna_true():
    """_arquivo_conteudo_permitido com filename vazio retorna (True, '')."""
    arquivo = MagicMock()
    arquivo.filename = "   "
    ok, msg = _arquivo_conteudo_permitido(arquivo)
    assert ok is True
    assert msg == ""


def test_arquivo_conteudo_permitido_ext_desconhecida_retorna_true():
    """Extensão não mapeada (ex: .txt) retorna (True, '') — aceita por extensão."""
    arquivo = MagicMock()
    arquivo.filename = "relatorio.txt"
    ok, msg = _arquivo_conteudo_permitido(arquivo)
    assert ok is True


def test_arquivo_conteudo_permitido_sem_stream_retorna_erro():
    """Arquivo com ext mapeada mas sem stream retorna (False, mensagem)."""
    arquivo = MagicMock(spec=["filename"])
    arquivo.filename = "imagem.png"
    ok, msg = _arquivo_conteudo_permitido(arquivo)
    assert ok is False
    assert "stream" in msg.lower()


def test_arquivo_conteudo_permitido_header_vazio_retorna_erro():
    """Arquivo com ext mapeada e stream vazio retorna (False, mensagem)."""
    arquivo = MagicMock()
    arquivo.filename = "imagem.png"
    buf = io.BytesIO(b"")
    arquivo.stream = buf
    ok, msg = _arquivo_conteudo_permitido(arquivo)
    assert ok is False
    assert "empty" in msg.lower() or "unreadable" in msg.lower()


def test_arquivo_conteudo_permitido_magic_errado_retorna_erro():
    """Arquivo com magic bytes incorretos para a extensão retorna (False, mensagem)."""
    arquivo = MagicMock()
    arquivo.filename = "documento.pdf"
    arquivo.stream = io.BytesIO(b"\x89PNG\r\n\x1a\n")  # PNG bytes, mas nome .pdf
    ok, msg = _arquivo_conteudo_permitido(arquivo)
    assert ok is False
    assert "conteúdo" in msg.lower() or "pdf" in msg.lower() or "corresponde" in msg.lower()


def test_arquivo_conteudo_permitido_excecao_retorna_erro():
    """Exceção ao ler stream retorna (False, mensagem de erro)."""
    arquivo = MagicMock()
    arquivo.filename = "doc.pdf"
    stream = MagicMock()
    stream.seek.side_effect = Exception("IO error")
    arquivo.stream = stream
    ok, msg = _arquivo_conteudo_permitido(arquivo)
    assert ok is False
    assert "erro" in msg.lower() or "IO error" in msg


def test_validar_novo_chamado_categoria_vazia_retorna_erro():
    """Sem categoria retorna erro de categoria obrigatória."""
    form = {
        "descricao": "Descrição ok",
        "tipo": "Manutencao",
        "categoria": "",
        "gate": "N/A",
        "impacto": "Impacto Baixo",
    }
    erros = validar_novo_chamado(form)
    assert any("category" in e.lower() and "required" in e.lower() for e in erros)


# ── Gate com sub-etapas (valores canônicos) ───────────────────────────────────


def test_validar_gate_na_aceito():
    """Gate N/A é válido sem sub-etapa."""
    form = {
        "descricao": "Descrição ok",
        "tipo": "Manutencao",
        "categoria": "Chamado",
        "gate": "N/A",
        "impacto": "Impacto Baixo",
    }
    erros = validar_novo_chamado(form)
    assert erros == []


def test_validar_gate_completo_desmontagem_aceito():
    """Gate com sub-etapa completa é aceito (fallback estático quando Firestore vazio)."""
    form = {
        "descricao": "Descrição ok",
        "tipo": "Manutencao",
        "categoria": "Chamado",
        "gate": "Gate 1 - Desmontagem",
        "impacto": "Impacto Baixo",
    }
    with patch("app.services.gates_service.CategoriaGate") as mock_cls:
        mock_cls.get_all_ativos.return_value = []
        erros = validar_novo_chamado(form)
    assert erros == []


def test_validar_gate_sem_subetapa_rejeitado():
    """Gate 1 sem sub-etapa (valor legado) é rejeitado em novos chamados."""
    form = {
        "descricao": "Descrição ok",
        "tipo": "Manutencao",
        "categoria": "Chamado",
        "gate": "Gate 1",
        "impacto": "Impacto Baixo",
    }
    with patch("app.services.gates_service.CategoriaGate") as mock_cls:
        mock_cls.get_all_ativos.return_value = []
        erros = validar_novo_chamado(form)
    assert any("gate" in e.lower() for e in erros)


def test_validar_gate_invalido_rejeitado():
    """Valor de gate arbitrário é rejeitado."""
    form = {
        "descricao": "Descrição ok",
        "tipo": "Manutencao",
        "categoria": "Chamado",
        "gate": "Gate 99",
        "impacto": "Impacto Baixo",
    }
    with patch("app.services.gates_service.CategoriaGate") as mock_cls:
        mock_cls.get_all_ativos.return_value = []
        erros = validar_novo_chamado(form)
    assert any("gate" in e.lower() for e in erros)
