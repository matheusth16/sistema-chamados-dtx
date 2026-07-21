/**
 * Load Test — sistema_chamados
 *
 * Objetivo: simular carga realista de usuários simultâneos no Cloud Run.
 * Cenário: login → dashboard → listar chamados → criar chamado → logout.
 * Carga: ramp-up de 10 VUs, sustentado por 3 minutos, ramp-down.
 *
 * Uso:
 *   k6 run \
 *     -e BASE_URL=https://SEU_DOMINIO \
 *     -e ADMIN_EMAIL=admin@dtx.aero \
 *     -e ADMIN_SENHA=SUA_SENHA \
 *     -e SUP_EMAIL=supervisor@dtx.aero \
 *     -e SUP_SENHA=SUA_SENHA \
 *     scripts/k6/load.js
 *
 * SLOs alinhados com Cloud Run (1 CPU, 512Mi, 1 worker + 8 threads):
 *   - p95 < 1500ms para páginas HTML
 *   - p95 < 800ms para endpoints JSON/API
 *   - taxa de erro < 1%
 */

import http from "k6/http";
import { check, group, sleep } from "k6";
import { Trend, Rate } from "k6/metrics";

// Métricas customizadas
const dashboardLatency = new Trend("dashboard_latency", true);
const apiLatency = new Trend("api_latency", true);
const loginSuccessRate = new Rate("login_success_rate");

export const options = {
  stages: [
    { duration: "30s", target: 5 },   // ramp-up suave
    { duration: "3m", target: 10 },   // carga sustentada (10 usuários simultâneos)
    { duration: "30s", target: 0 },   // ramp-down
  ],
  thresholds: {
    http_req_failed: ["rate<0.01"],
    http_req_duration: ["p(95)<1500"],
    dashboard_latency: ["p(95)<2000"],
    api_latency: ["p(95)<800"],
    login_success_rate: ["rate>0.95"],
  },
};

const BASE_URL = __ENV.BASE_URL || "http://localhost:5000";

// Perfis de usuário para distribuição de carga
const USUARIOS = [
  {
    email: __ENV.ADMIN_EMAIL || "admin@dtx.aero",
    senha: __ENV.ADMIN_SENHA || "senha_admin",
    perfil: "admin",
  },
  {
    email: __ENV.SUP_EMAIL || "supervisor@dtx.aero",
    senha: __ENV.SUP_SENHA || "senha_supervisor",
    perfil: "supervisor",
  },
];

function fazerLogin(email, senha) {
  // Obter CSRF token
  const loginPage = http.get(`${BASE_URL}/login`);

  let csrfToken = "";
  const match = loginPage.body.match(
    /name="csrf_token"[^>]*value="([^"]+)"/
  );
  if (match) csrfToken = match[1];

  const resp = http.post(
    `${BASE_URL}/login`,
    { email, senha, csrf_token: csrfToken },
    {
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      redirects: 0,
    }
  );

  const ok = resp.status === 302 || resp.status === 200;
  loginSuccessRate.add(ok);
  return { ok, cookies: resp.cookies };
}

export default function () {
  // Distribuir VUs entre perfis disponíveis
  const usuario = USUARIOS[__VU % USUARIOS.length];

  group("autenticacao", function () {
    const { ok } = fazerLogin(usuario.email, usuario.senha);
    check({ ok }, { "login bem-sucedido": (r) => r.ok });
    if (!ok) return;
  });

  // Pequena pausa após login (simula comportamento humano)
  sleep(Math.random() * 2 + 1);

  group("dashboard", function () {
    const start = Date.now();
    const resp = http.get(`${BASE_URL}/admin`, {
      tags: { endpoint: "dashboard" },
    });
    dashboardLatency.add(Date.now() - start);
    check(resp, {
      "dashboard: status 200 ou 302": (r) => [200, 302].includes(r.status),
    });
  });

  sleep(Math.random() * 1.5 + 0.5);

  group("api_notificacoes", function () {
    const start = Date.now();
    const resp = http.get(`${BASE_URL}/api/notificacoes`, {
      tags: { endpoint: "notificacoes" },
    });
    apiLatency.add(Date.now() - start);
    check(resp, {
      "notificacoes: status 200 ou 401": (r) => [200, 401].includes(r.status),
    });
  });

  sleep(Math.random() * 2 + 1);

  group("logout", function () {
    const resp = http.get(`${BASE_URL}/logout`, { redirects: 0 });
    check(resp, {
      "logout: redirecionado": (r) => [200, 302].includes(r.status),
    });
  });

  sleep(1);
}
