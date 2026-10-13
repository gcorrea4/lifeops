# Relatório completo de testes do LifeOps

Período: 10/10/2026 a 13/10/2026. Este relatório consolida todos os testes feitos nesta frente de trabalho. Resultados anteriores continuam registrados nos documentos históricos (`demo-validation-report.md`, `watsonx-validation-plan.md`, `BOB-DEVELOPMENT-LOG.md`); nada aqui os substitui.

## 1. Ambiente e método

- **Backend:** FastAPI + SQLAlchemy em contêiner Docker (Python 3.12, `ibm-watsonx-ai` 1.8.0). **Banco:** MySQL 8 de desenvolvimento. **Frontend:** React + TypeScript + Vite (servidor de desenvolvimento).
- **IA real:** IBM watsonx, região Sydney, modelo `meta-llama/llama-3-3-70b-instruct`, contrato final de dois campos (o modelo só devolve `recommended_candidate_id` e `explanation`; os `reason_codes` são calculados pelo backend).
- **Como a UI foi testada:** navegador embutido do app. Os campos e botões foram acionados por **eventos de DOM** (digitação e clique nos mesmos elementos da página), e o resultado foi conferido no DOM e no MySQL. Não foram usados cliques reais do mouse na maioria dos casos, e só um navegador (Chromium embutido) foi usado.
- **Dados:** todos os registros de teste tinham prefixo "DEMO" e foram removidos ao final. Ficaram apenas os seus dados reais: tarefa 10 "Trabalho", agendamento 4 e recomendação 6.
- **Chamadas reais ao watsonx na sessão:** cerca de 24 (10 da amostra sintética, 3 do smoke e 11 recomendações pelo app). Todas com `fallback_used=false`.

## 2. Resultados por área

### 2.1 Testes automáticos
| Teste | Data | Resultado |
|---|---|---|
| Backend (pytest, SQLite em memória) | 10/10 | 216 passed, 1 skipped |
| Backend após a correção do cascata | 13/10 | **217 passed, 1 skipped** (inclui o teste de regressão) |
| Smoke real do watsonx (`test_watsonx_provider`) | 10/10, 13/10 (2×) | 1 passed em todas |
| Frontend `npm run build` | várias | OK em todas |
| Frontend `npm run lint` | várias | OK (saída 0) em todas |

O único teste "skipped" é o smoke real, que só roda com credenciais. Warnings conhecidos: SQLAlchemy (coluna de data nullable em `fixed_block.py`) e licença de modelo de terceiros do watsonx.

### 2.2 Revalidação do watsonx no contrato final (10/10)
- Amostra sintética de 10 cenários direto no PlannerAgent (sem banco): **10/10 respostas válidas, 0 fallbacks, sem campos extras**, códigos derivados corretamente em todos (inclui `DEADLINE_CLOSE` no dia do prazo e no dia anterior, `ONLY_SLOT_AVAILABLE` com um candidato, nenhum código de prazo com prazo distante).
- O modelo escolheu o candidato 0 em 6 de 10 cenários.

### 2.3 Fluxo persistido pela API (10/10)
Compromissos 3 e 4, tarefa 9, recomendação 5, agendamento 3. Recomendação `201`, `fallback_used=false`, provider `watsonx`, códigos HIGH_PRIORITY, EARLIEST_SLOT, DEADLINE_CLOSE. Decisão MODIFIED (12:00–13:00) deixou a tarefa `pending` e sem agendamento; `/engine/book` deu `201`, tarefa `scheduled`, horário igual ao escolhido.

### 2.4 Fluxos pela UI
| Fluxo | Idioma | Resultado |
|---|---|---|
| Criar tarefa e compromisso | PT, EN | OK (mensagens de sucesso, listas atualizadas) |
| Recomendação real, candidatos, códigos com tooltip, indicador de fallback | PT, EN | OK |
| **Modificar** → decisão registrada com tarefa pendente → agendar | PT (12/10 e 13/10), EN | OK; banco confirmou `MODIFIED`, horário final igual ao escolhido |
| **Aprovar** → agendar (sem escolher candidato) | PT, EN | OK; horário final igual ao recomendado |
| **Rejeitar** (sem botão de agendar, horário final nulo) | PT, EN | OK; `REJECTED`, zero agendamentos, tarefa `pending` |
| Nova recomendação na mesma tarefa | EN | OK; novo snapshot, estado da rejeição limpo |
| Recarregar a página no meio do fluxo | EN | Fluxo local some (por desenho); idioma, tema e tarefa continuam |
| Trocar de tarefa no planejador | PT | Estado anterior descartado, sem vazamento |
| Mesmo estado em EN/PT, claro/escuro | todas as combinações | OK |

### 2.5 Validações e erros
| Caso | Resultado |
|---|---|
| Título vazio | Botão "Criar" desabilitado |
| Prazo no passado | HTTP 422, nada criado. **Em PT estava em inglês; corrigido** (ver 3.4) |
| Compromisso com horários iguais | Erro de cliente traduzido, nada criado |
| Tarefa de 900 min (não cabe em nenhum horário) | HTTP 422 traduzido; **nenhuma recomendação criada** (a IA não é chamada) |
| Reagendar tarefa já agendada | 409 `task is not pending`, nada gravado |
| Segunda decisão na mesma recomendação | 409 `decision already recorded…`, nada gravado |
| Recomendar para tarefa já agendada | 409, nada gravado |
| **Conflito de agendamento** | Modifiquei para 16:00–17:00, criei pela UI um compromisso 15:30–17:30 e tentei agendar: **HTTP 409 traduzido** ("O horário conflita com um compromisso fixo"), decisão e botão preservados, nenhum agendamento criado |
| **Recuperação do conflito** | Nova recomendação evitou 15:30–17:30 (lista saltou de 14:00 para 17:30); aprovada e agendada |

### 2.6 Compromissos
Semanal (sábado, quarta) e único que cruza a meia-noite com aviso "Termina no dia seguinte". Rótulos corretos em EN ("Every Saturday") e PT ("Todo sábado", "Toda quarta-feira"). O motor evitou os horários bloqueados e os agendamentos existentes.

### 2.7 Interface (tema, idioma, template)
- **Idioma EN/PT:** troca sem recarregar, preferência salva, idioma do navegador como padrão, todos os textos de interface traduzidos.
- **Tema claro/escuro:** troca sem recarregar, persistência após reload, segue o sistema quando não há escolha salva, foco por teclado visível nos dois temas, botão com `aria-label`.
- **Redesign Massively:** build/lint OK, fontes carregadas, âncoras do menu rolam para a seção certa, item ativo acompanha cliques e rolagem, layout em tela estreita sem rolagem horizontal.
- **Contraste:** cerca de 40 pares texto/fundo medidos nos dois temas; todos ≥ 4,5:1 depois das correções (menor valor 5,16 no claro e 6,87 no escuro).
- **Aviso de prazo expirado:** testado com lista simulada (a API recusa tarefa nova com prazo passado): selo "Prazo expirado" + botão "Planejar" desabilitado e riscado; tarefas válidas, sem prazo, com prazo hoje e agendadas com prazo passado não mudam; a tarefa expirada some do seletor do planejador.

### 2.8 Banco e limpeza
- Backup completo (`mysqldump`) antes de qualquer exclusão: `C:\Users\Gabriel\Backups\lifeops\lifeops-pre-cleanup-20261013-090037.sql` (17 KB, "Dump completed", 4 tabelas).
- Exclusão dos registros antigos de teste pela API; tarefa 10, agendamento 4 e recomendação 6 preservados.
- Exclusões de tarefas **com agendamento** deram 204 em 5 ocasiões depois da correção (tarefas 12, 14, 15, 17, 19), validando o cascata.
- Estado final: 1 tarefa (10), 0 compromissos, 1 agendamento (4), 1 recomendação (6). Próximos IDs: tarefa 20, compromisso 11, agendamento 11, recomendação 17.

### 2.9 Recomendações de IA geradas nos testes (todas removidas, exceto a 6)
| Rec. | Uso | Decisão |
|---|---|---|
| 5 | API, 10/10 | MODIFIED, agendada |
| 7 | UI PT, 12/10 | MODIFIED, agendada |
| 8 | UI PT, 13/10 | MODIFIED, agendada |
| 9 / 10 | UI PT | REJECTED / APPROVED (agendada) |
| 11 | UI EN | MODIFIED, agendada |
| 12 / 13 | UI EN | REJECTED / sem decisão (reload) |
| 14 | UI EN | APPROVED, agendada |
| 15 / 16 | UI PT, conflito | MODIFIED (409, não agendada) / APPROVED (agendada) |

## 3. Problemas encontrados

| # | Problema | Situação |
|---|---|---|
| 1 | **Imagem do contêiner desatualizada** (duas vezes: 10/10 com contrato antigo, 13/10 sem a correção do cascata). Uma demo nela não validaria o código atual | Contêiner reconstruído (`docker compose up -d --build api`); comparar hashes antes de demos |
| 2 | **`DELETE /tasks/{id}` dava 500 com agendamento** (ORM zerava `task_id` antes do cascata do banco; nada era apagado pela metade) | **Corrigido** pela sessão paralela (`ec8355c`) com teste de regressão; validado com exclusões 204 |
| 3 | **Explicação do modelo imprecisa** (rec. 8: "Earliest slot before deadline" para um horário que não era o primeiro). Os códigos estavam corretos | Limite conhecido do texto livre; códigos são do backend |
| 4 | Erro de prazo passado em inglês em PT (formato `campo: Value error, …` do Pydantic) | **Corrigido** em `api/client.ts` |
| 5 | Destaque do menu ficava preso em "Planejar" | **Corrigido** (`useActiveSection`) |
| 6 | Contraste do título da recomendação no tema claro (4,4:1) | **Corrigido** (cor de texto `#0a7295`) |
| 7 | "Toda sábado/domingo" em PT | **Corrigido** (acordo de gênero) |
| 8 | `.env` lido relativo ao diretório atual: rodar de `backend/` cai em mock sem avisar | Documentado; rodar sempre da raiz |
| 9 | Relógio do contêiner em UTC (host em UTC-3); a UI não envia `from_date`, então "hoje" e o corte de horários futuros seguem o relógio do contêiner | Limitação conhecida, documentada |
| 10 | `public/favicon.svg` referenciado e inexistente | Em aberto (sem efeito no fluxo) |
| 11 | Em EN, o erro de validação mostra o texto técnico do Pydantic | Em aberto, aceito |

Os "erros" do console do navegador durante os testes foram as respostas HTTP provocadas de propósito (422 e 409); não houve erro de JavaScript.

## 4. Não testado ou com cobertura limitada

- Cliques reais do mouse e navegação completa só por teclado.
- Outros navegadores além do Chromium embutido; telas reais de celular (usei emulação de largura).
- Teste automatizado de interface (não existe runner de testes no frontend).
- Agendamento que atravessa a meia-noite (o motor recusa; coberto na suíte do backend) e conflito entre dois agendamentos (coberto no backend).
- Falha real do provedor de IA e o caminho de fallback na UI (o fallback real só ocorreu no teste de 07/10, antes do contrato final).
- Desempenho e carga; segurança (não há autenticação, `user_id` fixo em 1); deploy em Azure/Vercel (ainda não feito).
- Fuso horário (datas continuam sem fuso, por decisão registrada).

## 5. Conclusão

O fluxo ponta a ponta (tarefa, compromissos, recomendação real do watsonx, decisão humana, agendamento explícito e revalidação) funcionou nos três caminhos de decisão, em português e inglês, nos dois temas, com o contrato final de dois campos e `fallback_used=false` em todas as chamadas reais. Os defeitos encontrados no caminho foram corrigidos ou documentados. As lacunas da seção 4 são o que ainda precisa de atenção antes de apresentar como pronto para produção; o projeto continua sendo um MVP sem autenticação e sem deploy.
