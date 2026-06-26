"""
Testes para validar_links_externos() e integração com validar_novo_chamado().

Feature: arquivos >10 MB → link OneDrive/SharePoint como alternativa ao upload.
"""

from app.services.validators import (
    ALLOWED_EXTERNAL_LINK_DOMAINS,
    validar_links_externos,
    validar_novo_chamado,
)

# ── ALLOWED_EXTERNAL_LINK_DOMAINS ─────────────────────────────────────────────


def test_dominios_permitidos_contem_sharepoint():
    assert "sharepoint.com" in ALLOWED_EXTERNAL_LINK_DOMAINS


def test_dominios_permitidos_contem_onedrive():
    assert "onedrive.live.com" in ALLOWED_EXTERNAL_LINK_DOMAINS


def test_dominios_permitidos_contem_1drv():
    assert "1drv.ms" in ALLOWED_EXTERNAL_LINK_DOMAINS


# ── validar_links_externos — entradas válidas ─────────────────────────────────


def test_lista_vazia_retorna_sem_erros():
    assert validar_links_externos([]) == []


def test_link_vazio_ignorado():
    assert validar_links_externos([""]) == []
    assert validar_links_externos(["  "]) == []


def test_sharepoint_valido():
    url = "https://dtxaerospace.sharepoint.com/sites/chamados/documento.pdf"
    assert validar_links_externos([url]) == []


def test_sharepoint_subdominio_valido():
    url = "https://dtxaerospace-my.sharepoint.com/:b:/g/personal/doc"
    assert validar_links_externos([url]) == []


def test_onedrive_live_valido():
    url = "https://onedrive.live.com/edit.aspx?resid=ABC123"
    assert validar_links_externos([url]) == []


def test_1drv_ms_valido():
    url = "https://1drv.ms/b/s!AkXY"
    assert validar_links_externos([url]) == []


def test_multiplos_links_validos():
    urls = [
        "https://empresa.sharepoint.com/arquivo1.xlsx",
        "https://1drv.ms/b/s!AkXY",
    ]
    assert validar_links_externos(urls) == []


# ── validar_links_externos — entradas inválidas ───────────────────────────────


def test_link_sem_https_retorna_erro():
    erros = validar_links_externos(["http://sharepoint.com/doc"])
    assert len(erros) == 1
    assert "https://" in erros[0]


def test_link_http_incorreto():
    erros = validar_links_externos(["ftp://sharepoint.com/doc"])
    assert len(erros) == 1


def test_dominio_invalido_google_drive():
    erros = validar_links_externos(["https://drive.google.com/file/abc"])
    assert len(erros) == 1
    assert "SharePoint" in erros[0] or "OneDrive" in erros[0]


def test_dominio_invalido_dropbox():
    erros = validar_links_externos(["https://www.dropbox.com/s/abc/file.pdf"])
    assert len(erros) == 1


def test_dominio_invalido_generico():
    erros = validar_links_externos(["https://exemplo.com.br/arquivo.pdf"])
    assert len(erros) == 1


def test_mix_valido_invalido_retorna_erros_dos_invalidos():
    urls = [
        "https://empresa.sharepoint.com/ok.xlsx",
        "https://drive.google.com/errado",
    ]
    erros = validar_links_externos(urls)
    assert len(erros) == 1


def test_link_sem_barra_apenas_dominio_invalido():
    erros = validar_links_externos(["https://sharepoint.com.evil.com/abc"])
    assert len(erros) == 1


def test_link_sharepoint_como_subdominio_falso_bloqueado():
    """sharepoint.com.hacker.org NÃO deve ser aceito."""
    erros = validar_links_externos(["https://sharepoint.com.hacker.org/file"])
    assert len(erros) == 1


# ── validar_novo_chamado com links_externos ───────────────────────────────────

_FORM_VALIDO = {
    "descricao": "Problema com impressora do 2º andar",
    "tipo": "Manutencao",
    "categoria": "Chamado",
    "gate": "N/A",
    "impacto": "Impacto Baixo",
}


def test_validar_novo_chamado_com_links_externos_validos():
    """Links OneDrive/SharePoint válidos não geram erros adicionais."""
    links = ["https://empresa.sharepoint.com/sites/chamados/doc.pdf"]
    erros = validar_novo_chamado(_FORM_VALIDO, links_externos=links)
    assert erros == []


def test_validar_novo_chamado_com_links_externos_invalidos():
    """Links inválidos geram erros na validação."""
    links = ["https://drive.google.com/errado"]
    erros = validar_novo_chamado(_FORM_VALIDO, links_externos=links)
    assert any("SharePoint" in e or "OneDrive" in e for e in erros)


def test_validar_novo_chamado_sem_links_externos_compativel():
    """Sem links_externos (None), comportamento original preservado."""
    erros = validar_novo_chamado(_FORM_VALIDO)
    assert erros == []


def test_validar_novo_chamado_links_externos_nenhum_valido():
    """Lista com link sem https gera erro."""
    links = ["http://sharepoint.com/inseguro"]
    erros = validar_novo_chamado(_FORM_VALIDO, links_externos=links)
    assert any("https://" in e for e in erros)


def test_validar_novo_chamado_links_externos_lista_vazia():
    """Lista vazia não gera erros."""
    erros = validar_novo_chamado(_FORM_VALIDO, links_externos=[])
    assert erros == []


def test_validar_novo_chamado_links_externos_ignorados_se_none():
    """links_externos=None → não executa validação de links."""
    erros = validar_novo_chamado(_FORM_VALIDO, links_externos=None)
    assert erros == []
