/**
 * Spike Test — pico curto e moderado para validar recuperação.
 * Duração total: 3m.
 *
 * Uso local:
 *   k6 run -e BASE_URL=http://127.0.0.1:5000 scripts/qa/k6/spike.js
 */

import http from "k6/http";
import { check, sleep } from "k6";
import { assertSafeTarget } from "./_shared.js";

export const options = {
  stages: [
    { duration: "30s", target: 3 },
    { duration: "15s", target: 15 },
    { duration: "45s", target: 15 },
    { duration: "30s", target: 3 },
    { duration: "1m", target: 0 },
  ],
  thresholds: {
    http_req_failed: ["rate<0.05"],
    http_req_duration: ["p(95)<3000"],
  },
};

const BASE_URL = assertSafeTarget(__ENV.BASE_URL || "http://127.0.0.1:5000");

export default function () {
  const response = http.get(`${BASE_URL}/health`);
  check(response, {
    "health responde 200 durante pico": (result) => result.status === 200,
  });
  sleep(0.5);
}
