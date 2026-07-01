# Product

## Register

product

## Users

- **Solicitante** — colaborador DTX que abre chamados (suporte, manutenção, solicitações internas) e acompanha o próprio histórico. Pode estar no escritório ou no chão de fábrica.
- **Supervisor** — gerencia os chamados da sua área, atualiza status, emite relatórios. Trabalha majoritariamente em escritório/sala de reunião.
- **Admin** — acesso total: chamados, usuários, categorias, traduções, relatórios globais.
- **Admin Global** — herda tudo de admin; governança entre áreas, promove/rebaixa admins e supervisores.

Dois ambientes físicos distintos usam o mesmo sistema: escritório (boa iluminação, mouse/teclado) e chão de fábrica (mecânicos e engenheiros, luz industrial, leitura rápida à distância, possivelmente com luvas).

## Product Purpose

DTX Service Portal — sistema interno de chamados da DTX Aerospace (o nome "Digital Andon" foi descontinuado; o nome oficial atual do produto é DTX Service Portal). Substitui processos informais de solicitação/acompanhamento por um fluxo único e auditável: abrir chamado, classificar por categoria, acompanhar status (Aberto → Em Andamento → Concluído/Cancelado), notificar partes interessadas (e-mail via Microsoft Graph + push web), e gerar relatórios de área. Sucesso = visibilidade em tempo real do estado de qualquer chamado, sem ambiguidade, para qualquer um dos dois públicos (escritório ou chão de fábrica).

## Brand Personality

**Confiança, controle, eficiência** — tema "Industrial Precision". Deve transmitir o rigor de uma operação aeroespacial, não a estética de um SaaS genérico.

Dois arquétipos visuais mapeiam os dois públicos, e o sistema deve atender ambos sem sacrificar nenhum:
- **Swiss Industrial Print** (light mode) — para supervisores/admins em escritório: hierarquia densa, tipografia bold, grid rígido.
- **Tactical Telemetry** (dark mode) — para mecânicos/engenheiros em chão de fábrica: contraste extremo, leitura a distância, tipografia funcional (IDs de chamado em monospace).

O toggle light/dark não é cosmético — é a principal feature de acessibilidade do sistema, dado o contexto físico dos dois públicos.

Referências de estilo (não anti-referências): Linear.app (hierarquia densa), Vercel Dashboard (superfícies diferenciadas), Notion (profundidade real nos cards).

## Anti-references

Não deve parecer um SaaS genérico — sem cards flutuantes sem propósito, sem paleta usada apenas como decoração, sem flat design sem hierarquia. Cor é dado (sinaliza ação/status), não enfeite.

## Design Principles

1. **Contraste com propósito** — cada superfície existe por uma razão, nunca decorativa.
2. **Cor como dado** — o azul DTX (e as cores de status) aparecem onde há ação ou significado, não como estilo.
3. **Tipografia dominante e funcional** — hierarquia pesada nos headings; monospace para IDs/timestamps/metadados técnicos.
4. **Dois públicos, um sistema** — toda decisão visual é testada contra escritório (light) E chão de fábrica (dark), nunca só uma.
5. **Densidade equilibrada** — breathing room nas páginas de navegação, compacidade nas tabelas de dados.

## Accessibility & Inclusion

- WCAG AA: contraste mínimo 4.5:1 (texto normal) e 3:1 (texto grande/UI).
- Focus ring visível (`focus-visible:ring-2`) em todos os elementos interativos.
- `prefers-reduced-motion` respeitado, especialmente nos badges pulsantes de status "Aberto".
- Dark mode segue `prefers-color-scheme` na primeira visita; escolha explícita do usuário prevalece via `localStorage`.
