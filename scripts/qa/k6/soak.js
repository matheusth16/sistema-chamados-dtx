/**
 * Soak Test — carga baixa e contínua para detectar degradação gradual.
 *
 * K6_DURATION controla a duração (padrão seguro: 15m).
 * Uso local:
 *   k6 run -e BASE_URL=http://127.0.0.1:5000 -e K6_DURATION=30m scripts/qa/k6/soak.js
 */

import http from "k6/http";
import { check, sleep } from "k6";
import { assertSafeTarget } from "./_shared.js";

export const options = {
  vus: 3,
  duration: __ENV.K6_DURATION || "15m",
  thresholds: {
    http_req_failed: ["rate<0.01"],
    http_req_duration: ["p(95)<2000"],
  },
};

const BASE_URL = assertSafeTarget(__ENV.BASE_URL || "http://127.0.0.1:5000");

export default function () {
  const health = http.get(`${BASE_URL}/health`);
  check(health, {
    "health responde 200": (result) => result.status === 200,
  });

  const login = http.get(`${BASE_URL}/login`);
  check(login, {
    "login responde 200": (result) => result.status === 200,
  });

  sleep(1);
}
