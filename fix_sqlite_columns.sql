-- Manual SQL fix for SQLite database
-- Run this if you're using SQLite locally and getting NOT NULL constraint errors
-- 
-- Usage: sqlite3 db.sqlite3 < fix_sqlite_columns.sql
--
-- This recreates the table without the old columns (num_recipes, num_meals, num_snacks)

BEGIN TRANSACTION;

-- Create new table without old columns
CREATE TABLE diet_planner_dietarygoal_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    prompt TEXT NOT NULL,
    dietary_restrictions TEXT,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    country VARCHAR(2) NOT NULL,
    city VARCHAR(100) NOT NULL,
    currency VARCHAR(3) NOT NULL DEFAULT 'PLN',
    language_code VARCHAR(5) NOT NULL DEFAULT 'pl',
    num_days INTEGER NOT NULL DEFAULT 7,
    main_courses_per_day INTEGER NOT NULL DEFAULT 1,
    small_meals_per_day INTEGER NOT NULL DEFAULT 2,
    snacks_per_day INTEGER NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    completed_at DATETIME,
    celery_task_id VARCHAR(255),
    user_id INTEGER NOT NULL REFERENCES auth_user(id)
);

-- Copy data (excluding old columns)
INSERT INTO diet_planner_dietarygoal_new 
SELECT 
    id, prompt, dietary_restrictions, status, country, city, currency, language_code,
    num_days, main_courses_per_day, small_meals_per_day, snacks_per_day,
    created_at, updated_at, completed_at, celery_task_id, user_id
FROM diet_planner_dietarygoal;

-- Drop old table
DROP TABLE diet_planner_dietarygoal;

-- Rename new table
ALTER TABLE diet_planner_dietarygoal_new RENAME TO diet_planner_dietarygoal;

-- Recreate indexes
CREATE INDEX diet_planne_user_id_267b95_idx ON diet_planner_dietarygoal(user_id, created_at DESC);
CREATE INDEX diet_planne_status_d14f37_idx ON diet_planner_dietarygoal(status);
CREATE INDEX diet_planne_country_f59cc6_idx ON diet_planner_dietarygoal(country);

COMMIT;




