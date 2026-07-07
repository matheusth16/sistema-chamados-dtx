"""Configuração do Gunicorn — carregada antes de qualquer worker/import da app.

Objetivo: evitar que o header HTTP `Server` identifique a tecnologia usada
(CWI checklist §7.1 — não expor Server: gunicorn/versão para reduzir
fingerprinting de infraestrutura por atacantes).
"""

import gunicorn

# Precisa ser setado aqui (antes do import de gunicorn.http.wsgi pelo arbiter/worker)
# para que o header "Server" saia genérico em vez de "gunicorn".
gunicorn.SERVER = "webserver"
gunicorn.SERVER_SOFTWARE = "webserver"
