/**
 * Stress Test — sistema_chamados
 *
 * Objetivo: encontrar o ponto de ruptura do Cloud Run (config atual: 1 CPU, 512Mi,
 * 1 worker + 8 threads). Aumenta VUs gradualmente até degradar ou falhar.
 *
 * Foca nos endpoints mais pesados:
 *   - /admin/relatorios (analytics completo — N queries Firestore)
 *   - /health (baseline: deve aguentar qualquer carga)
 *
 * Uso:
 *   k6 run \
 *     -e BASE_URL=https://SEU_DOMINIO \
 *     -e ADMIN_EMAIL=admin@dtx.aero \
 *     -e ADMIN_SENHA=SUA_SENHA \
 *     scripts/k6/stress.js
 *
 * Interprete os resultados:
 *   - A partir de qual VU o p95 cruza 3s? → gargalo
 *   - A partir de qual VU a taxa de erro cruza 5%? → limite de ruptura
 *   - O Cloud Run reiniciou algum container? → checar logs
 */

import http from "k6/http";
import { check, sleep } from "k6";
import { Trend, Rate } from "k6/metrics";

const relatoriosLatency = new Trend("relatorios_latency", true);
const healthLatency = new Trend("health_latency", true);
const errorRate = new Rate("custom_error_rate");

export const options = {
  stages: [
    { duration: "1m", target: 5 },
    { duration: "1m", target: 10 },
    { duration: "1m", target: 20 },
    { duration: "1m", target: 30 },   // Além da capacidade esperada
    { duration: "2m", target: 30 },   // Sustenta para ver comportamento estável
    { duration: "1m", target: 0 },
  ],
  thresholds: {
    // Sem abortagem automática — queremos observar a degradação completa
    http_req_failed: ["rate<0.30"],    // Tolera até 30% de erro no stress test
    health_latency: ["p(99)<500"],     // Health check deve aguentar sempre
  },
};

const BASE_URL = __ENV.BASE_URL || "http://localhost:5000";

// Sessão simples — health check não precisa de login
export default function () {
  // 1. Health check (referência — deve ser sempre rápido)
  const hStart = Date.now();
  const health = http.get(`${BASE_URL}/health`);
  healthLatency.add(Date.now() - hStart);
  const healthOk = check(health, {
    "health: 200": (r) => r.status === 200,
  });
  errorRate.add(!healthOk);

  sleep(0.5);

  // 2. Login rápido + página de dashboard (sem autenticar = 302 para login, testa roteamento)
  const rStart = Date.now();
  const dashboard = http.get(`${BASE_URL}/admin`, { redirects: 0 });
  relatoriosLatency.add(Date.now() - rStart);
  check(dashboard, {
    "dashboard: responde (200/302)": (r) => [200, 302].includes(r.status),
  });

  sleep(Math.random() * 2);
}
