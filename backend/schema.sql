-- FitCheck.AI database (MySQL 8, utf8mb4)
-- Swayam Shakya
-- Every table that holds a person's data references users(id) ON DELETE CASCADE,
-- so deleting an account removes everything that belongs to it.

CREATE TABLE IF NOT EXISTS users (
  id            INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  email         VARCHAR(254) NOT NULL,
  password_hash VARCHAR(255) NOT NULL,
  display_name  VARCHAR(60)  NOT NULL,
  created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_users_email (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;

-- sign-in sessions: only a SHA-256 of the token is stored
CREATE TABLE IF NOT EXISTS sessions (
  id            INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  user_id       INT UNSIGNED NOT NULL,
  token_hash    CHAR(64) NOT NULL,
  created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  last_seen_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  expires_at    DATETIME NOT NULL,
  remember      TINYINT(1) NOT NULL DEFAULT 0,
  revoked_at    DATETIME NULL,
  user_agent    VARCHAR(160) NULL,
  UNIQUE KEY uq_sessions_token (token_hash),
  KEY ix_sessions_user (user_id),
  CONSTRAINT fk_sessions_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- failed sign-ins and photo requests, for rate limits (keys are hashed)
CREATE TABLE IF NOT EXISTS rate_events (
  id         BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  bucket     VARCHAR(20) NOT NULL,
  key_hash   CHAR(64) NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY ix_rate (bucket, key_hash, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- one-time password-reset links; only the token's SHA-256 is stored
CREATE TABLE IF NOT EXISTS password_resets (
  id          INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  user_id     INT UNSIGNED NOT NULL,
  token_hash  CHAR(64) NOT NULL,
  created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  expires_at  DATETIME NOT NULL,
  used_at     DATETIME NULL,
  UNIQUE KEY uq_resets_token (token_hash),
  KEY ix_resets_user (user_id),
  CONSTRAINT fk_resets_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS preferences (
  user_id INT UNSIGNED PRIMARY KEY,
  data    JSON NOT NULL,
  CONSTRAINT fk_prefs_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- photo-service keys, encrypted (Fernet: AES-128-CBC + HMAC-SHA256) with a key derived from SECRET_KEY
CREATE TABLE IF NOT EXISTS secrets (
  user_id    INT UNSIGNED PRIMARY KEY,
  engine     VARCHAR(10) NOT NULL DEFAULT 'free',
  sealed     VARBINARY(4096) NULL,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CONSTRAINT ck_secrets_engine CHECK (engine IN ('free', 'gemini')),
  CONSTRAINT fk_secrets_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- images: garment photos, cut-outs and AI outfit photos (user_id NULL = public landing-page photo)
CREATE TABLE IF NOT EXISTS images (
  id         INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  ikey       CHAR(32) NOT NULL,
  user_id    INT UNSIGNED NULL,
  mime       VARCHAR(20) NOT NULL,
  data       MEDIUMBLOB NOT NULL,
  cache_key  CHAR(64) NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_images_key (ikey),
  KEY ix_images_user (user_id),
  KEY ix_images_cache (cache_key),
  CONSTRAINT ck_images_mime CHECK (mime IN ('image/jpeg', 'image/png', 'image/webp')),
  CONSTRAINT fk_images_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS items (
  id                   INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  user_id              INT UNSIGNED NOT NULL,
  name                 VARCHAR(80)  NOT NULL,
  category             VARCHAR(12)  NOT NULL,
  subcategory          VARCHAR(40)  NOT NULL,
  main_color_hex       CHAR(7)      NOT NULL,
  main_color_name      VARCHAR(20)  NOT NULL,
  secondary_color_hex  CHAR(7)      NULL,
  secondary_color_name VARCHAR(20)  NULL,
  pattern              VARCHAR(10)  NOT NULL DEFAULT '',
  seasons              JSON NOT NULL,
  style                VARCHAR(20)  NOT NULL,
  occasions            JSON NOT NULL,
  description          VARCHAR(500) NOT NULL DEFAULT '',
  image_key            CHAR(32) NULL,
  cutout_key           CHAR(32) NULL,
  image_source         VARCHAR(8) NULL,
  created_at           DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at           DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  deleted_at           DATETIME NULL,
  KEY ix_items_user (user_id, deleted_at),
  CONSTRAINT ck_items_category CHECK (category IN ('top','bottom','dress','outerwear','footwear','accessory')),
  CONSTRAINT ck_items_hex CHECK (main_color_hex REGEXP '^#[0-9a-f]{6}$'),
  CONSTRAINT ck_items_hex2 CHECK (secondary_color_hex IS NULL OR secondary_color_hex REGEXP '^#[0-9a-f]{6}$'),
  CONSTRAINT ck_items_source CHECK (image_source IS NULL OR image_source IN ('upload','stock')),
  CONSTRAINT ck_items_pattern CHECK (pattern IN ('','striped','patterned')),
  CONSTRAINT fk_items_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS outfits (
  id            INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  user_id       INT UNSIGNED NOT NULL,
  occasion      VARCHAR(12) NOT NULL,
  weather       VARCHAR(8)  NOT NULL,
  temperature_c DECIMAL(4,1) NOT NULL,
  style_pref    VARCHAR(20) NULL,
  palette_pref  VARCHAR(12) NOT NULL DEFAULT 'any',
  score         TINYINT UNSIGNED NOT NULL,
  breakdown     JSON NOT NULL,
  explanation   TEXT NOT NULL,
  signature     VARCHAR(255) NOT NULL,
  engine        VARCHAR(8) NOT NULL,
  photo_cover   INT UNSIGNED NULL,
  worn_at       DATETIME NULL,
  created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY ix_outfits_user (user_id, created_at),
  CONSTRAINT ck_outfits_score CHECK (score <= 100),
  CONSTRAINT ck_outfits_temp CHECK (temperature_c BETWEEN -40 AND 50),
  CONSTRAINT fk_outfits_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS outfit_items (
  outfit_id INT UNSIGNED NOT NULL,
  item_id   INT UNSIGNED NOT NULL,
  role      VARCHAR(12) NOT NULL,
  position  TINYINT UNSIGNED NOT NULL,
  PRIMARY KEY (outfit_id, item_id),
  CONSTRAINT fk_oi_outfit FOREIGN KEY (outfit_id) REFERENCES outfits(id) ON DELETE CASCADE,
  CONSTRAINT fk_oi_item FOREIGN KEY (item_id) REFERENCES items(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- the AI photos of an outfit (an outfit keeps its last four takes)
CREATE TABLE IF NOT EXISTS outfit_photos (
  id         INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  outfit_id  INT UNSIGNED NOT NULL,
  image_key  CHAR(32) NOT NULL,
  model      VARCHAR(80) NULL,
  created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  KEY ix_photos_outfit (outfit_id),
  CONSTRAINT fk_photos_outfit FOREIGN KEY (outfit_id) REFERENCES outfits(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS feedback (
  outfit_id  INT UNSIGNED PRIMARY KEY,
  user_id    INT UNSIGNED NOT NULL,
  verdict    VARCHAR(8) NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  KEY ix_feedback_user (user_id),
  CONSTRAINT ck_feedback_verdict CHECK (verdict IN ('like','dislike')),
  CONSTRAINT fk_feedback_outfit FOREIGN KEY (outfit_id) REFERENCES outfits(id) ON DELETE CASCADE,
  CONSTRAINT fk_feedback_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS saved_outfits (
  id         INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  user_id    INT UNSIGNED NOT NULL,
  outfit_id  INT UNSIGNED NOT NULL,
  name       VARCHAR(80) NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_saved_outfit (outfit_id),
  KEY ix_saved_user (user_id),
  CONSTRAINT fk_saved_outfit FOREIGN KEY (outfit_id) REFERENCES outfits(id) ON DELETE CASCADE,
  CONSTRAINT fk_saved_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
