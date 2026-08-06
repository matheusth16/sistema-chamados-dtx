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

# Socket de controle (gunicornc — gerenciar workers via CLI) introduzido no
# Gunicorn 25.1.0, habilitado por padrão. Tenta criar o socket num diretório
# protegido (achado 2026-08-06 rodando em produção: "Control server error:
# Permission denied: '/home/appuser'") — o container roda como usuário
# não-root e não tem permissão de escrita lá. Sem efeito funcional (não
# usamos gunicornc: o container é gerenciado via Docker/Watchtower, não via
# sinais gunicorn), mas gera um [ERROR] no log a cada restart, poluindo
# os playbooks de troubleshooting baseados em padrão de log
# (docs/INCIDENT_RUNBOOK.md, docs/QA_DEBUG_PLAYBOOK.md). Desativado.
control_socket_disable = True
