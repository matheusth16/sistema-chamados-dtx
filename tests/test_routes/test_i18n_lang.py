"""F-61: Teste HTTP — parâmetro ?lang=xyz inválido não deve causar 500 nem gravar código inválido na sessão."""


def test_lang_invalido_retorna_200_e_sessao_fallback_en(client):
    """F-61: GET /login?lang=xyz deve retornar 200 e gravar en na sessão (fallback)."""
    r = client.get("/login?lang=xyz")
    assert r.status_code == 200, f"Esperado 200, recebido {r.status_code}"

    with client.session_transaction() as sess:
        lang = sess.get("language")
    assert lang == "en", f"session['language'] deveria ser 'en' para ?lang=xyz, mas foi {lang!r}"


def test_lang_valido_pt_br_e_gravado_corretamente(client):
    """GET /login?lang=pt_BR grava pt_BR na sessão."""
    r = client.get("/login?lang=pt_BR")
    assert r.status_code == 200

    with client.session_transaction() as sess:
        assert sess.get("language") == "pt_BR"


def test_lang_valido_en_e_gravado_corretamente(client):
    """GET /login?lang=en grava en na sessão."""
    r = client.get("/login?lang=en")
    assert r.status_code == 200

    with client.session_transaction() as sess:
        assert sess.get("language") == "en"


def test_sem_lang_sessao_usa_padrao_en(client):
    """F-61: Sem ?lang e sem sessão prévia, o padrão deve ser en."""
    r = client.get("/login")
    assert r.status_code == 200

    with client.session_transaction() as sess:
        lang = sess.get("language")
    assert lang == "en", f"Padrão deveria ser 'en', mas foi {lang!r}"
