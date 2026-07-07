"""Testa que gunicorn.conf.py neutraliza o header Server (CWI §7.1 — sem fingerprint de infra)."""

import runpy

import gunicorn


def test_gunicorn_conf_neutraliza_server_header():
    """Carregar gunicorn.conf.py deve sobrescrever gunicorn.SERVER/SERVER_SOFTWARE."""
    original_server = gunicorn.SERVER
    original_software = gunicorn.SERVER_SOFTWARE
    try:
        runpy.run_path("gunicorn.conf.py")
        assert gunicorn.SERVER == "webserver"
        assert gunicorn.SERVER_SOFTWARE == "webserver"
    finally:
        gunicorn.SERVER = original_server
        gunicorn.SERVER_SOFTWARE = original_software
