CREATE TABLE IF NOT EXISTS shops (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  campus TEXT NOT NULL,
  area TEXT,
  poi_id TEXT,
  address TEXT,
  category TEXT,
  geo_source TEXT,
  geo_score REAL,
  latitude REAL,
  longitude REAL,
  avg_price INTEGER NOT NULL,
  open_hours TEXT,
  tastes TEXT,
  scenes TEXT,
  tags TEXT,
  is_open INTEGER DEFAULT 1,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS recommendation_logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  raw_query TEXT NOT NULL,
  parsed_json TEXT NOT NULL,
  result_json TEXT NOT NULL,
  engine TEXT NOT NULL DEFAULT 'rule-based',
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS usage_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  event_type TEXT NOT NULL, -- query | ranking_click
  uid TEXT,
  anonymous_id TEXT,
  user_id TEXT,
  query_text TEXT,
  shop_id TEXT,
  shop_name TEXT,
  source TEXT DEFAULT 'web',
  meta_json TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_usage_events_type_time
  ON usage_events(event_type, created_at);

CREATE INDEX IF NOT EXISTS idx_usage_events_shop_time
  ON usage_events(shop_id, created_at);

CREATE TABLE IF NOT EXISTS feedback_submissions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  feedback_type TEXT NOT NULL, -- new_store | dining_feedback
  store_name TEXT NOT NULL,
  anonymous_id TEXT,
  user_id TEXT,
  area TEXT,
  category TEXT,
  avg_price INTEGER,
  rating INTEGER,
  scene_tags TEXT,
  taste_tags TEXT,
  feature_tags TEXT,
  recommend_dish TEXT,
  short_intro TEXT,
  recommend_reason TEXT,
  comment TEXT,
  warning_note TEXT,
  source TEXT DEFAULT 'frontend_user_feedback',
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_feedback_type_time
  ON feedback_submissions(feedback_type, created_at);

CREATE INDEX IF NOT EXISTS idx_feedback_store_time
  ON feedback_submissions(store_name, created_at);

CREATE TABLE IF NOT EXISTS user_favorites (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id TEXT NOT NULL,
  anonymous_id TEXT,
  shop_id TEXT NOT NULL,
  shop_name TEXT,
  source TEXT DEFAULT 'web',
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(user_id, shop_id)
);

CREATE INDEX IF NOT EXISTS idx_favorites_user_time
  ON user_favorites(user_id, created_at);
