/**
 * Smoke Test — sistema_chamados
 *
 * Objetivo: confirmar que o serviço está no ar antes de rodar testes maiores.
 * Carga: 1 VU, 30 segundos.
 *
 * Uso:
 *   k6 run -e BASE_URL=https://SEU_DOMINIO scripts/k6/smoke.js
 *   k6 run -e BASE_URL=http://localhost:5000 scripts/k6/smoke.js
 */

import http from "k6/http";
import { check, sleep } from "k6";

export const options = {
  vus: 1,
  duration: "30s",
  thresholds: {
    http_req_failed: ["rate<0.01"],        // Menos de 1% de erros
    http_req_duration: ["p(95)<2000"],     // p95 < 2s
  },
};

const BASE_URL = __ENV.BASE_URL || "http://localhost:5000";

export default function () {
  // 1. Health check
  const health = http.get(`${BASE_URL}/health`);
  check(health, {
    "health: status 200": (r) => r.status === 200,
    "health: body ok": (r) => {
      try {
        return JSON.parse(r.body).status === "ok";
      } catch {
        return false;
      }
    },
  });

  // 2. Página de login acessível (sem autenticação)
  const login = http.get(`${BASE_URL}/login`);
  check(login, {
    "login: status 200": (r) => r.status === 200,
    "login: contém formulário": (r) => r.body.includes("email") || r.body.includes("login"),
  });

  sleep(1);
}
