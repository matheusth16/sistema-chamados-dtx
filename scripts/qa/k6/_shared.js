/**
 * Proteções compartilhadas dos testes k6.
 *
 * Qualquer alvo remoto é bloqueado por padrão. Para executar deliberadamente
 * contra staging/produção, informe K6_CONFIRM_PROD=1 no mesmo comando.
 */

const LOCAL_HOSTS = ["localhost", "127.0.0.1"];

export function assertSafeTarget(rawUrl) {
  const baseUrl = String(rawUrl || "").trim().replace(/\/+$/, "");
  const match = /^https?:\/\/(\[[^\]]+\]|[^/:?#]+)(?::\d+)?(?:[/?#]|$)/i.exec(baseUrl);

  if (!match) {
    throw new Error(
      "BASE_URL inválida: use uma URL absoluta http(s), por exemplo http://127.0.0.1:5000."
    );
  }

  const hostname = match[1].toLowerCase().replace(/^\[|\]$/g, "");
  if (!LOCAL_HOSTS.includes(hostname) && __ENV.K6_CONFIRM_PROD !== "1") {
    throw new Error(
      `Alvo remoto bloqueado (${hostname}). Defina K6_CONFIRM_PROD=1 somente após confirmar o ambiente.`
    );
  }

  return baseUrl;
}
