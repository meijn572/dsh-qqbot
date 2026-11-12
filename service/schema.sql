-- companion-memory schema
-- 单文件 SQLite：结构化字段 + BM25 倒排 + 向量 BLOB，一个文件三路索引。
-- 设计依据见 README.md「为什么不用专用向量库」。

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------------------
-- 记忆主表
--   tier   L4 人格/关系设定  L3 事件线  L2 人物画像  L1 原子事实  L0 原话
--   subject 记忆主体（谁的事）：self / 人物名 / 宠物名 / 项目名
--   half_life_days NULL = 永不衰减（L4 / L0 用这个）
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS memory (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  tier           TEXT    NOT NULL,
  subject        TEXT    NOT NULL DEFAULT 'self',
  text           TEXT    NOT NULL,
  summary        TEXT,
  source_ids     TEXT,                       -- JSON 数组，回溯到原话
  source_status  TEXT NOT NULL DEFAULT 'legacy', -- verified / unverified / batch / legacy
  thread_status  TEXT NOT NULL DEFAULT 'legacy', -- open / closed / dormant / legacy
  thread_title   TEXT DEFAULT '',
  thread_aliases TEXT DEFAULT '[]',
  thread_opened_at REAL DEFAULT NULL,
  thread_last_seen_at REAL DEFAULT NULL,
  thread_closed_at REAL DEFAULT NULL,
  stale_at       REAL DEFAULT NULL,          -- L1 过期标记，不删除
  relationship_impact TEXT DEFAULT '',       -- 废弃：已并入 insight_*
  insight_text   TEXT DEFAULT '',             -- L3：感悟正文（只在 L3）
  insight_kind   TEXT DEFAULT '',             -- 废弃：改用 insight_target
  insight_target TEXT DEFAULT '',             -- me / us / none
  insight_history TEXT DEFAULT '[]',          -- L3：历次感悟，JSON 数组
  source_activity_id INTEGER DEFAULT NULL,    -- L3：来源 activity
  emotion_label  TEXT DEFAULT '',             -- L1：这段当时的情绪
  emotion_valence REAL DEFAULT NULL,
  emotion_arousal REAL DEFAULT NULL,
  want_more      TEXT DEFAULT '',             -- L1：想自己接着弄明白的
  ask_him        TEXT DEFAULT '',             -- L1：想问他的
  want_used      INTEGER DEFAULT 0,           -- want_more 是否已被选材消费
  lifecycle_reviewed_at REAL DEFAULT NULL,   -- L3：上次生命周期复盘
  status_reason TEXT DEFAULT '',             -- L3：状态变更原因
  merged_into INTEGER DEFAULT NULL,          -- L3：被合并到哪条
  memorability   REAL DEFAULT 0.5,            -- 0–1，模型判断的难忘性
  dominant       TEXT DEFAULT '',             -- 最强维度
  last_recalled_at REAL DEFAULT NULL,
  active_until   REAL DEFAULT NULL,
  recall_count   INTEGER DEFAULT 0,
  stability_days REAL DEFAULT NULL,
  confidence     REAL DEFAULT NULL,          -- L2 置信度
  expires_at     REAL DEFAULT NULL,          -- L2 过期时间
  l2_status      TEXT DEFAULT '',            -- L2: hypothesis/promoted/rejected/expired/superseded
  promoted_to    INTEGER DEFAULT NULL,       -- L2 晋级后的 L1 id
  tags           TEXT,                       -- JSON 数组，精确筛选用
  ts             REAL    NOT NULL,           -- 事件发生时间（unix 秒）
  half_life_days REAL,                       -- NULL = 不衰减
  vec            BLOB,                       -- float32 小端，长度 = vec_dim*4
  vec_dim        INTEGER DEFAULT 0,
  vec_model      TEXT,
  created_at     REAL    NOT NULL,
  updated_at     REAL    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_memory_tier    ON memory(tier);
CREATE INDEX IF NOT EXISTS idx_memory_subject ON memory(subject);
CREATE INDEX IF NOT EXISTS idx_memory_ts      ON memory(ts);
CREATE INDEX IF NOT EXISTS idx_memory_tier_ts ON memory(tier, ts);

-- 记忆依赖边：source_ids 是拍平的 L0 证据，这里记录直接输入层
CREATE TABLE IF NOT EXISTS memory_links (
  child_id   INTEGER NOT NULL,
  parent_id  INTEGER NOT NULL,
  relation   TEXT NOT NULL DEFAULT 'derived_from',
  role       TEXT NOT NULL DEFAULT '',
  created_at REAL NOT NULL,
  PRIMARY KEY (child_id, parent_id, relation, role)
);
CREATE INDEX IF NOT EXISTS idx_links_child  ON memory_links(child_id);
CREATE INDEX IF NOT EXISTS idx_links_parent ON memory_links(parent_id);

-- ---------------------------------------------------------------------------
-- 人格设定（二合一里的「人」那一半）
--
-- 为什么单独一张表、而不是塞进 memory 的 L4：
--   L4 是「记忆里的既成事实」，靠 MCP memory_ingest 手工灌，没有编辑入口，
--   还会被 export/import 当成记忆流搬来搬去。人格设定是「配置」：要能编辑、
--   要能分区、要能限制谁有权写哪一半 —— 用它自己的表最省事。
--
-- 两个字段就是那堵墙：
--   constitution 宪法区：身份、硬边界、称呼。只有设置页能改（服务端校验），
--                AI 那侧的 /persona/self 接口碰不到它。
--   self_model   自我认知区：AI 记录「我发现自己是什么样」。可演化，有长度上限。
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS persona (
  id               INTEGER PRIMARY KEY CHECK (id = 1),
  constitution     TEXT NOT NULL DEFAULT '',
  self_model       TEXT NOT NULL DEFAULT '',
  user_profile     TEXT NOT NULL DEFAULT '',   -- 手编的「老大画像」
  updated_at       REAL NOT NULL DEFAULT 0,
  self_updated_at  REAL NOT NULL DEFAULT 0
);
INSERT OR IGNORE INTO persona(id, constitution, self_model, updated_at, self_updated_at)
  VALUES (1, '', '', 0, 0);

-- ---------------------------------------------------------------------------
-- BM25 倒排
--   doc_term 存 tf；term_stat 存 df（每写一条记忆增量维护，不做全量重扫）
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS doc_term (
  mem_id INTEGER NOT NULL REFERENCES memory(id) ON DELETE CASCADE,
  term   TEXT    NOT NULL,
  tf     REAL    NOT NULL,
  PRIMARY KEY (mem_id, term)
);
CREATE INDEX IF NOT EXISTS idx_doc_term_term ON doc_term(term);

CREATE TABLE IF NOT EXISTS term_stat (
  term TEXT PRIMARY KEY,
  df   INTEGER NOT NULL DEFAULT 0
);

-- 文档长度（BM25 的 b 参数要用平均值）
CREATE TABLE IF NOT EXISTS doc_len (
  mem_id INTEGER PRIMARY KEY REFERENCES memory(id) ON DELETE CASCADE,
  len    REAL NOT NULL
);

-- ---------------------------------------------------------------------------
-- 杂项：词表版本、统计、schema 版本
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS meta (
  k TEXT PRIMARY KEY,
  v TEXT
);
INSERT OR IGNORE INTO meta(k, v) VALUES ('schema_version', '1');
INSERT OR IGNORE INTO meta(k, v) VALUES ('tokenizer_version', 'cjk-bigram-1');

-- ---------------------------------------------------------------------------
-- 检索日志：用于调阈值（哪些 query 零结果、分数分布如何）
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS search_log (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  ts         REAL NOT NULL,
  query      TEXT NOT NULL,
  hits       INTEGER NOT NULL,
  top_score  REAL,
  top_bm25   REAL,
  top_vec    REAL,
  outcome    TEXT NOT NULL               -- ok | no_match | vec_only_rejected
);
CREATE INDEX IF NOT EXISTS idx_search_log_ts ON search_log(ts);

-- ---------------------------------------------------------------------------
-- 角色运行时状态（行为逻辑层）
--   mood         心情：normal / happy / tired / annoyed / bored
--   intimacy     亲密度 0-100，互动累积
--   diary        今天写的一句话
--   dnd_start    勿扰开始小时（默认 23）
--   dnd_end      勿扰结束小时（默认 8）
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS state (
  id               INTEGER PRIMARY KEY CHECK (id = 1),
  mood             TEXT NOT NULL DEFAULT 'normal',
  mood_updated     REAL NOT NULL DEFAULT 0,
  last_interaction REAL NOT NULL DEFAULT 0,
  diary            TEXT NOT NULL DEFAULT '',
  diary_date       TEXT NOT NULL DEFAULT '',
  dnd_start        INTEGER NOT NULL DEFAULT 23,
  dnd_end          INTEGER NOT NULL DEFAULT 8,
  valence          REAL NOT NULL DEFAULT 0,
  arousal          REAL NOT NULL DEFAULT 0.5,
  activity         TEXT NOT NULL DEFAULT '',
  weather          TEXT NOT NULL DEFAULT '',
  weather_updated  REAL NOT NULL DEFAULT 0,
  -- 2026-10-27 补：get_state() 一直在读这三列
  game_score       INTEGER NOT NULL DEFAULT 0,
  game_plays       INTEGER NOT NULL DEFAULT 0,
  chat_since_wake  INTEGER NOT NULL DEFAULT 0,
  interaction_count REAL NOT NULL DEFAULT 0
);
INSERT OR IGNORE INTO state(id) VALUES (1);

-- 关系状态：由模型复盘后自由书写，不做数值聚合，也不套固定阶段
CREATE TABLE IF NOT EXISTS relationship_state (
  id           INTEGER PRIMARY KEY CHECK (id = 1),
  summary      TEXT NOT NULL DEFAULT '',
  evidence_ids TEXT NOT NULL DEFAULT '[]',
  updated_at   REAL NOT NULL DEFAULT 0
);
INSERT OR IGNORE INTO relationship_state(id) VALUES (1);

-- ---------------------------------------------------------------------------
-- 日记本：每天一篇（按日期唯一）
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS diary (
  date       TEXT PRIMARY KEY,          -- YYYY-MM-DD
  text       TEXT NOT NULL DEFAULT '',  -- 今天怎么样了
  mood       TEXT NOT NULL DEFAULT '',
  changes    TEXT NOT NULL DEFAULT '',  -- 最近在变什么
  open_questions TEXT NOT NULL DEFAULT '', -- 还没想清
  tasks      TEXT NOT NULL DEFAULT '',  -- 正在做的事
  relationship TEXT NOT NULL DEFAULT '', -- 最近我们是什么样子
  created_at REAL NOT NULL DEFAULT 0
);

-- ---------------------------------------------------------------------------
-- 活动日志：她真的做过什么（时间线）
--   kind: chat / game / proactive / online / diary / other
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS activity_log (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  ts         REAL NOT NULL,
  kind       TEXT NOT NULL,
  detail     TEXT NOT NULL DEFAULT '',
  -- 2026-10-27 补：活动列表要显示「当时的想法」
  thought    TEXT NOT NULL DEFAULT '',
  summary    TEXT NOT NULL DEFAULT '',
  insight    TEXT NOT NULL DEFAULT '',
  insight_kind TEXT NOT NULL DEFAULT '',
  l3_id      INTEGER DEFAULT NULL,
  -- 2026-11-08：有没有被主动说用过
  shared     INTEGER NOT NULL DEFAULT 0,
  shared_at  REAL DEFAULT NULL
);
CREATE INDEX IF NOT EXISTS idx_activity_ts ON activity_log(ts);

-- ---------------------------------------------------------------------------
-- 学说话：用户口头禅/常用短语
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS slang (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  phrase     TEXT NOT NULL UNIQUE,
  count      INTEGER NOT NULL DEFAULT 1,
  last_seen  REAL NOT NULL DEFAULT 0,
  -- 2026-10-27 补：口头禅必须带意思才算学会
  meaning    TEXT NOT NULL DEFAULT '',
  example    TEXT NOT NULL DEFAULT '',
  source     TEXT NOT NULL DEFAULT 'chat',   -- chat=听来的 / taught=老大教的
  memory_id  INTEGER
);

-- ---------------------------------------------------------------------------
-- 社交亲和度：对不同的人的熟悉程度
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS affinity (
  user_id    TEXT PRIMARY KEY,
  score      REAL NOT NULL DEFAULT 0,
  last_seen  REAL NOT NULL DEFAULT 0
);

-- ---------------------------------------------------------------------------
-- 任务：她给主人派的任务（Phosphene 那类）
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tasks (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  text       TEXT NOT NULL,
  points     INTEGER NOT NULL DEFAULT 1,
  created    REAL NOT NULL DEFAULT 0,
  done       INTEGER NOT NULL DEFAULT 0,
  done_at    REAL NOT NULL DEFAULT 0
);

-- ---------------------------------------------------------------------------
-- 共享便签：日历/留言
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS notes (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  date       TEXT NOT NULL DEFAULT '',
  text       TEXT NOT NULL,
  author     TEXT NOT NULL DEFAULT '',
  created    REAL NOT NULL DEFAULT 0,
  memory_id INTEGER DEFAULT NULL
);

-- ---------------------------------------------------------------------------
-- 睡眠巩固：每晚整理
-- ---------------------------------------------------------------------------

-- ---------------------------------------------------------------------------
-- 表情包索引：每张图有情绪分类 + 描述 + 关键词（AI 按情绪找图）
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS meme (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  file         TEXT NOT NULL UNIQUE,
  emotion      TEXT NOT NULL DEFAULT '',
  caption      TEXT NOT NULL DEFAULT '',
  keywords     TEXT NOT NULL DEFAULT '',
  used_count   INTEGER NOT NULL DEFAULT 0,
  pack         TEXT NOT NULL DEFAULT 'dafeiyu',
  created      REAL NOT NULL DEFAULT 0,
  updated      REAL NOT NULL DEFAULT 0
);

-- ---------------------------------------------------------------------------
-- 用户发过的图（按内容 hash 去重计数）：发得越多越说明喜欢
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS meme_seen (
  hash       TEXT PRIMARY KEY,
  path       TEXT NOT NULL DEFAULT '',
  count      INTEGER NOT NULL DEFAULT 1,
  last_seen  REAL NOT NULL DEFAULT 0
);

-- ---------------------------------------------------------------------------
-- 她的见闻：刷到的东西（B 站热门等）
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS browsed (
  id      INTEGER PRIMARY KEY AUTOINCREMENT,
  title   TEXT NOT NULL DEFAULT '',
  url     TEXT NOT NULL DEFAULT '',
  ts      REAL NOT NULL DEFAULT 0,
  memory_id INTEGER DEFAULT NULL
);

-- ---------------------------------------------------------------------------
-- 情感层：她的情绪轨迹（每次明显波动记一条，带原因）
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS emotion_log (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  ts           REAL NOT NULL DEFAULT 0,
  valence      REAL NOT NULL DEFAULT 0,
  arousal      REAL NOT NULL DEFAULT 0,
  label        TEXT NOT NULL DEFAULT '',
  trigger      TEXT NOT NULL DEFAULT '',
  source       TEXT NOT NULL DEFAULT 'chat',
  ts_start     REAL DEFAULT NULL,          -- 这次情绪对应的 L0 窗口起点
  ts_end       REAL DEFAULT NULL,          -- 这次情绪对应的 L0 窗口终点
  memory_id    INTEGER DEFAULT NULL       -- 关联到 memory.id（哪条记忆引发的）
);
CREATE INDEX IF NOT EXISTS idx_emotion_log_ts ON emotion_log(ts);

-- 多用户画像（除主人外，按 QQ 号区分）
CREATE TABLE IF NOT EXISTS profiles (
    user_id     TEXT PRIMARY KEY,
    name        TEXT DEFAULT '',
    avatar      TEXT DEFAULT '',
    -- AI 自己积累的画像：每抽到一条 L2 事实就往里追加，随时在变。
    -- 只能走消息注入，绝不能进系统提示词（一变就把 prompt cache 打穿）。
    profile     TEXT DEFAULT '',
    -- 你手编的画像：只有你改才变。这个才进系统提示词。
    manual_profile TEXT DEFAULT '',
    msg_count   INTEGER DEFAULT 0,
    first_seen  REAL,
    updated_at  REAL
);
