-- =============================================================================
-- migration_add_proctor_video_quality_setting.sql
-- =============================================================================
-- Adds an admin-configurable video-recording quality tier for proctoring
-- (screen + webcam recordings — see VIDEO_QUALITY_PRESETS in
-- proctoring_feature.py) to an existing database (one already created from an
-- earlier version of schema_clean.sql or schema_demo.sql, with data you want
-- to keep). Safe to run once.
--
-- proctor_settings is a single-row table (id is always 1) rather than a
-- generic key/value store, since this is currently the only proctoring-wide
-- setting an admin can change. get_proctor_video_quality()/
-- set_proctor_video_quality() in proctoring_feature.py read/write this row;
-- the Admin Panel's Maintenance tab (app.py) is the only place it's set from.
--
-- Changing the tier only affects proctoring sessions that start (browser
-- permission granted) after the change — it's read once when a session's
-- screen/webcam recording begins, not re-applied to a recording already in
-- progress.
--
-- Run with:
--   mysql -u <user> -p streamlit_database < migration_add_proctor_video_quality_setting.sql
-- =============================================================================

CREATE TABLE proctor_settings (
    id            INT PRIMARY KEY DEFAULT 1,
    video_quality ENUM('low', 'medium', 'high') NOT NULL DEFAULT 'medium',
    updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO proctor_settings (id, video_quality) VALUES (1, 'medium');
