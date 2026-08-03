---
description: "Task list for WhatsApp 企业知识问答助手 1.0"
---

# Tasks: WhatsApp 企业知识问答助手 1.0

**Input**: Design documents from `/specs/001-whatsapp-rag-assistant/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/webhook.md, quickstart.md

**Tests**: 包含单元测试。宪法要求 RAG 核心（pipeline 检索/生成、chunking、store 存取）可自动化验证；会话、限流、幂等、指令识别等纯逻辑模块同样用 pytest 覆盖。RAG 真实命中率/阈值标定走 quickstart 手动步骤，不写依赖外部服务的集成测试。

**Organization**: 任务按用户故事分组，每个故事可独立实现与测试。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 可并行（不同文件、不依赖未完成任务）
- **[Story]**: 所属用户故事（US1~US7）
- 所有任务含明确文件路径

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: 测试框架与依赖准备。项目骨架已存在，仅补齐测试依赖。

- [X] T001 将 `pytest` 加入 [requirements.txt](requirements.txt)，并创建 `tests/` 目录及 `tests/__init__.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: 所有用户故事共用的配置、工具与基础设施。

**⚠️ CRITICAL**: 本阶段完成前，不开始任何用户故事。

- [X] T002 扩展 [app/config.py](app/config.py) 的 `Settings`，新增：`session_ttl_seconds`、`session_max_turns`、`session_max_chars`、`rag_score_threshold`、`answer_max_chars`、`rate_limit_per_minute`、`message_max_chars`、`on_duty_number`、`on_duty_fallback_number`，全部从环境变量读取并给默认值；同步更新 [.env.example](.env.example)（FR-033/034）
- [X] T003 [P] 创建 [app/observability.py](app/observability.py)：`new_request_id()`、`mask_waid(wa_id)`（号码脱敏）、结构化日志辅助（关键字段：request_id、waid 脱敏、问题、命中数、top_score、是否回答、耗时、异常），不得记录密钥/完整号码（FR-030/031）
- [X] T004 [P] 扩展 [app/rag/store.py](app/rag/store.py)：新增 `count_points()`（返回 collection 点数）与 `clear_collection()`（清空全部 point，用于全量重建与空库判断）
- [X] T005 [P] 在 [app/rag/ingest.py](app/rag/ingest.py) 实现全量重建：入库前调用 `clear_collection()`，payload 增加 `chunk_index`，返回总切片数；空/无法读取的文件明确报错不静默跳过（FR-008）
- [X] T006 [P] 创建 [app/commands.py](app/commands.py)：识别指令类型——`help`（帮助/help/菜单）、`reset`（重新开始/清空/新话题）、`handoff`（转人工/找人工）、`feedback`（👍/👎），返回结构化结果；未命中返回 None
- [X] T007 [P] 创建 [tests/test_commands.py](tests/test_commands.py)，覆盖各类指令与表情的识别、未命中、大小写/前后空格
- [X] T008 [P] 创建 [app/guards.py](app/guards.py)：`IdempotencyGuard`（基于 MessageSid，24h TTL，进程内 dict+锁）、`RateLimiter`（按 WAID 的 60s 固定窗口计数）、`check_message_length(body)`（超长判定），均支持惰性过期清理（FR-025/026/027）
- [X] T009 [P] 创建 [tests/test_guards.py](tests/test_guards.py)，覆盖幂等重复丢弃、TTL 过期、限流窗口翻窗与超限、长度边界
- [X] T010 创建 [app/session.py](app/session.py)：`SessionStore`（进程内 dict+锁），提供读取（含 7 天过期判定，返回是否过期）、追加轮次（截断最近 N 轮）、组装上下文（累计字符 ≤ 上限，超出丢弃最早轮）、清空、`miss_streak` 增减与归零、记录"最后一条助手消息是否已评价"（FR-009~014）
- [X] T011 [P] 创建 [tests/test_session.py](tests/test_session.py)，覆盖滑动过期、10 轮截断、2000 字符截断、清空、miss_streak、已评价标记
- [X] T012 重构 [app/main.py](app/main.py) 的 webhook 骨架：解析 `MessageSid`/`From`/`Body`，立即返回空 200，后台任务依次执行幂等→长度校验→限流（超限/超长直接回提示），接入 observability 日志；空 Body 安全忽略（FR-028/029）
- [X] T013 增强 [app/main.py](app/main.py) 的 `/health`：返回服务存活与知识库状态（collection 名、点数、accessible），不泄露敏感信息（FR-032）

**Checkpoint**: 基础设施就绪。guards/session/commands/observability 均可独立单测，webhook 能即时回 200 并做幂等/限流/长度拦截。

---

## Phase 3: User Story 1 - 基于知识库回答客户问题 (Priority: P1) 🎯 MVP

**Goal**: 客户提问，系统检索知识库并生成带来源、长度受控的回答；空库时明确提示。

**Independent Test**: 通过 `/ask` 或 WhatsApp 问一个知识库内问题，验证回答准确、附来源、长度受限；空库时提示"知识库尚未就绪"。

- [X] T014 [P] [US1] 创建 [tests/test_pipeline.py](tests/test_pipeline.py)：mock 掉 embedding/检索/LLM 客户端，覆盖"命中→回答+来源"、"空库→empty_kb"、"答案长度截断"
- [X] T015 [US1] 重构 [app/rag/pipeline.py](app/rag/pipeline.py)：定义并返回 `AnswerResult`（reply、sources、status、top_score、need_handoff）；基于检索结果拼接上下文与来源；按 `answer_max_chars` 控制长度；空库返回 `empty_kb`；system prompt 强制基于资料作答并标注来源（FR-001/003/004/006）
- [X] T016 [US1] 在 [app/main.py](app/main.py) 的 `_handle` 中接入 pipeline：正常回答后发送答案+来源列表+反馈提示，把 user/assistant 轮次写入 session；更新 `/ask` 返回结构化字段（answer/sources/status/top_score）

**Checkpoint**: US1 独立可用——核心问答闭环跑通（对应 SC-001/SC-002/SC-005）。

---

## Phase 4: User Story 2 - 知识库无答案时明确拒答 (Priority: P1)

**Goal**: 相关性不足或知识库外问题时拒答，不编造。

**Independent Test**: 问无关问题，验证返回拒答话术、不调用 LLM 编造、不附虚假来源；连续 2 次为自动转人工铺垫。

- [X] T017 [P] [US2] 在 [tests/test_pipeline.py](tests/test_pipeline.py) 增加阈值拒答用例：最高分低于 `rag_score_threshold` 时返回 `no_match`
- [X] T018 [US2] 在 [app/rag/pipeline.py](app/rag/pipeline.py) 实现阈值判断：取最高检索分，低于阈值直接返回 `no_match`（不调用 LLM）；在 [app/main.py](app/main.py) 返回统一拒答话术，并对该 session 的 `miss_streak` +1，成功回答时归零（FR-002/005）

**Checkpoint**: US1+US2 共同保证"答得准、不编造"（对应 SC-003）。

---

## Phase 5: User Story 3 - 多轮连续追问 (Priority: P1)

**Goal**: 结合最近对话理解指代与上下文，支持手动重置。

**Independent Test**: 问"年假几天"再问"那病假呢"，验证第二问结合上文；发"重新开始"清空会话。

- [X] T019 [P] [US3] 在 [tests/test_pipeline.py](tests/test_pipeline.py) 增加多轮历史用例：历史以多轮 messages 传入；验证按轮数/字符截断后送入 LLM 的内容
- [X] T020 [US3] 在 [app/rag/pipeline.py](app/rag/pipeline.py) 让 `answer()` 接收 `history` 参数，构造多轮 `messages`（system 含知识上下文，历史 user/assistant 轮，最后当前问题）
- [X] T021 [US3] 在 [app/main.py](app/main.py) 接入会话：回答前用 `SessionStore` 取历史，回答后追加本轮并刷新 TTL；处理 `reset` 指令清空会话并回复确认（FR-009/011/012/013）

**Checkpoint**: 多轮追问与重置可用。

---

## Phase 6: User Story 4 - 跨天与跨设备继续对话 (Priority: P2)

**Goal**: 7 天滑动过期；同账号跨设备共享会话；过期后不假装记得。

**Independent Test**: 调小 TTL 验证过期后收到"已重新开始"；同账号在两台设备发消息上下文连续。

- [X] T022 [US4] 在 [app/main.py](app/main.py) 处理会话过期：`SessionStore` 判定过期时清空并回复"已重新开始，请再说一下你的问题"，不基于旧上下文作答；跨设备共享由 wa_id 作为会话键天然保证（FR-010/014）

**Checkpoint**: 跨天/跨设备行为符合预期；跨设备无需额外代码（会话键即 WAID）。

---

## Phase 7: User Story 5 - 转人工 (Priority: P2)

**Goal**: 主动或自动（连续 2 次未答出）触发转人工，通知值班号码并告知客户。

**Independent Test**: 发"转人工"验证值班号收到含上下文的通知、客户收到确认；主号失败时试备用号；未配置时优雅降级。

- [X] T023 [P] [US5] 创建 [app/handoff.py](app/handoff.py)：组装通知（客户号码、最后问题、最近若干轮/2000 字符内上下文、触发原因、时间），经 [app/channel.py](app/channel.py) 发送给 `on_duty_number`，失败时尝试 `on_duty_fallback_number`（FR-015/017）
- [X] T024 [P] [US5] 创建 [tests/test_handoff.py](tests/test_handoff.py)：mock 通道发送，验证上下文组装、主号失败回退备用号、未配置号码的降级（FR-018）
- [X] T025 [US5] 在 [app/main.py](app/main.py) 接线：命中 `handoff` 指令触发；`miss_streak >= 2` 时主动提示并触发；回复客户"已通知值班人员"；1.0 不做双向中继（FR-016/019）

**Checkpoint**: 转人工端到端可用。

---

## Phase 8: User Story 6 - 新用户引导与帮助 (Priority: P3)

**Goal**: 新用户首条消息收欢迎语；帮助指令返回功能说明。

**Independent Test**: 新号码首次发消息收到欢迎语+示例；发"帮助"收到菜单。

- [X] T026 [P] [US6] 创建 [app/responses.py](app/responses.py)：集中维护欢迎语、帮助菜单、拒答、转人工确认、限流、超长、错误提示等话术文案（便于业务方确认措辞）
- [X] T027 [US6] 在 [app/main.py](app/main.py) 实现：无会话记录的号码首条非指令消息回欢迎语+示例；命中 `help` 指令回帮助菜单（FR-020/021）

**Checkpoint**: 引导与帮助可用。

---

## Phase 9: User Story 7 - 答案反馈 (Priority: P3)

**Goal**: 客户可 👍/👎 评价，反馈记日志，同一轮不重复计数。

**Independent Test**: 回答后回复 👍 验证日志记录；重复表情只记一次。

- [X] T028 [US7] 在 [app/main.py](app/main.py) 处理 `feedback` 指令：识别 👍/👎，通过 observability 记录（脱敏 waid、问题、回答摘要、来源、时间、request_id）；用 session 的"已评价"标记防止同轮重复记录；回复感谢提示（FR-022/023）

**Checkpoint**: 反馈闭环可用。

---

## Phase 10: Polish & Cross-Cutting Concerns

**Purpose**: 文档、全量验证与宪法合规复核。

- [X] T029 [P] 更新 [README.md](README.md)：单 worker 运行要求（`--workers 1`）、新增配置项与 `.env.example`、新增模块说明、1.0 功能列表、重启清空会话的限制
- [X] T030 [P] 全局隐私复核：grep 检查日志与源码中无硬编码密钥、完整手机号、Auth Token（FR-031/033，宪法原则 III/IV）
- [X] T031 运行 `pytest -q` 全绿；按 [quickstart.md](specs/001-whatsapp-rag-assistant/quickstart.md) 跑完 4.1~4.15 端到端场景，重点核验：webhook 毫秒级回 200、回答带来源、阈值拒答、幂等不重复回复、限流、转人工、异常兜底不崩溃
- [X] T032 宪法合规复核：逐条核验原则 I（带来源/拒答/无黑盒框架）、II（即时 200）、III（密钥走环境变量）、IV（日志脱敏+异常兜底）、V（无 Redis/DB/任务队列、Qdrant 本地、单 worker）

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**：无依赖，立即开始。
- **Foundational (Phase 2)**：依赖 Phase 1；阻塞所有用户故事。
- **US1 (Phase 3, P1)**：依赖 Foundational；MVP 核心，无故事间依赖。
- **US2 (Phase 4, P1)**：依赖 US1（改同一 pipeline 与 main）。
- **US3 (Phase 5, P1)**：依赖 US1（pipeline 增加 history；session 在 Foundational 已建）。
- **US4 (Phase 6, P2)**：依赖 US3（会话过期处理在主流程接线后才有意义）。
- **US5 (Phase 7, P2)**：依赖 US2（miss_streak 在拒答阶段引入）。
- **US6 (Phase 8, P3)**：依赖 Foundational，可与 US3~US5 并行（主要改 main/新增 responses）。
- **US7 (Phase 9, P3)**：依赖 US1（需要"最后一条助手消息"上下文）。
- **Polish (Phase 10)**：依赖所有目标故事完成。

### User Story Dependencies

- **US1 (P1)**：Foundational 后即可开始，是 MVP。
- **US2 (P1)**：紧接 US1（共享 pipeline.py/main.py）。
- **US3 (P1)**：紧接 US1。
- **US4 (P2)**：依赖 US3。
- **US5 (P2)**：依赖 US2。
- **US6 (P3)**：相对独立，Foundational 后可并行。
- **US7 (P3)**：依赖 US1。

### Within Each User Story

- 测试任务先写并确认失败，再写实现（纯逻辑模块）。
- pipeline 改动先于 main 接线。
- 故事完成后对照 quickstart 相应场景独立验证。

### Parallel Opportunities

- T003/T004/T005/T006/T008/T010/T011 互不共写文件，Foundational 阶段可并行。
- 各故事的测试文件（T007/T009/T011/T014/T017/T019/T024）可与对应实现并行准备。
- US6（T026/T027，responses.py + main）可在 US3~US5 进行时并行，但注意 main.py 合并（单人按顺序更稳妥）。

> 注意：多数故事最终都改 [app/main.py](app/main.py) 与 [app/rag/pipeline.py](app/rag/pipeline.py)。单人开发建议按 P1→P2→P3 顺序执行以避免同文件冲突；多人并行时以 main.py 的编排函数为界分工并频繁合并。

---

## Parallel Example: Foundational Phase

```bash
# 以下任务互不共写文件，可同时开展：
Task: "T003 创建 app/observability.py"
Task: "T004 扩展 app/rag/store.py（count/clear）"
Task: "T006 创建 app/commands.py"
Task: "T008 创建 app/guards.py"
Task: "T010 创建 app/session.py"

# 对应测试也可并行：
Task: "T007 tests/test_commands.py"
Task: "T009 tests/test_guards.py"
Task: "T011 tests/test_session.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 + US2 核心可信)

1. 完成 Phase 1 + Phase 2（基础设施）
2. 完成 Phase 3（US1 问答闭环）+ Phase 4（US2 拒答）
3. **停下来验证**：通过 `/ask` 与 WhatsApp 验证命中/拒答/来源/长度
4. 此时已可演示：能答知识库内问题、不编造、带来源

### Incremental Delivery

1. Setup + Foundational → 平台就绪
2. US1 + US2 → 可信问答 MVP
3. US3 + US4 → 多轮/跨天，体验完整
4. US5 → 转人工兜底
5. US6 + US7 → 引导与反馈
6. Polish → 文档、隐私复核、quickstart 全量验证
7. 每个故事独立验证，不破坏前序故事

### Parallel Team Strategy

- 全体先完成 Foundational。
- 完成后：A 负责 US1/US2（pipeline 主线），B 负责 US6/US7（responses + 反馈，注意与 main.py 协调），C 负责 US5（handoff.py 独立）。
- US3/US4 依赖 pipeline 历史改造，建议由 US1 负责人延续。

---

## Notes

- [P] = 不同文件、无未完成依赖。
- [Story] 标签映射到 spec.md 的 US1~US7。
- 必须以 `uvicorn --workers 1` 运行（会话/幂等/限流在进程内存）。
- 每个任务或逻辑组完成后提交（约定式提交前缀）。
- 避免：模糊任务、同文件冲突、破坏故事独立性的跨故事依赖。
- 阈值 `RAG_SCORE_THRESHOLD` 默认 0.5 仅为起点，上线前按 quickstart 第 5 节用真实知识库标定。
