-- ============================================================
-- PostgreSQL DDL Script for Derisk
-- Version: 0.3.0
-- Generated: 2026-08-01T19:26:32.852225
-- ============================================================

-- Table: chat_history
CREATE TABLE IF NOT EXISTS "chat_history" (
  "id" SERIAL,
  "conv_uid" VARCHAR(255) NOT NULL,
  "chat_mode" VARCHAR(255) NOT NULL,
  "summary" TEXT NOT NULL,
  "user_name" VARCHAR(255),
  "messages" TEXT,
  "message_ids" TEXT,
  "sys_code" VARCHAR(128),
  "gmt_create" TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  "gmt_modified" TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  "app_code" VARCHAR(255),
  "workspace_id" INTEGER,
  "task_id" INTEGER,
  PRIMARY KEY ("id"),
  CONSTRAINT "uk_conv_uid" UNIQUE ("conv_uid")
);
CREATE INDEX "ix_chat_history_workspace_id" ON "chat_history" ("workspace_id");
CREATE INDEX "ix_chat_history_sys_code" ON "chat_history" ("sys_code");
CREATE INDEX "ix_chat_history_task_id" ON "chat_history" ("task_id");

-- Table: chat_history_message
CREATE TABLE IF NOT EXISTS "chat_history_message" (
  "id" SERIAL,
  "conv_uid" VARCHAR(255) NOT NULL,
  "index" INTEGER NOT NULL,
  "round_index" INTEGER NOT NULL,
  "message_detail" TEXT,
  "gmt_create" TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  "gmt_modified" TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY ("id"),
  CONSTRAINT "uk_conversation_message" UNIQUE ("conv_uid", "index")
);

-- Table: server_app_artifact
CREATE TABLE IF NOT EXISTS "server_app_artifact" (
  "id" SERIAL,
  "task_id" INTEGER NOT NULL,
  "workspace_id" INTEGER NOT NULL,
  "type" VARCHAR(32) NOT NULL,
  "title" VARCHAR(256) NOT NULL,
  "content_ref" VARCHAR(512),
  "content_text" TEXT,
  "current_version" INTEGER NOT NULL DEFAULT true,
  "provenance_json" TEXT,
  "is_shared" BOOLEAN NOT NULL DEFAULT false,
  "created_by_agent" VARCHAR(128),
  "created_by_user" INTEGER,
  "gmt_create" TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  "gmt_modified" TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY ("id")
);
CREATE INDEX "ix_server_app_artifact_task_id" ON "server_app_artifact" ("task_id");
CREATE INDEX "ix_server_app_artifact_workspace_id" ON "server_app_artifact" ("workspace_id");

-- Table: server_app_artifact_version
CREATE TABLE IF NOT EXISTS "server_app_artifact_version" (
  "id" SERIAL,
  "artifact_id" INTEGER NOT NULL,
  "version" INTEGER NOT NULL,
  "content_ref" VARCHAR(512),
  "diff_summary" TEXT,
  "created_by" VARCHAR(128),
  "gmt_create" TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY ("id")
);
CREATE INDEX "ix_server_app_artifact_version_artifact_id" ON "server_app_artifact_version" ("artifact_id");
CREATE UNIQUE INDEX "uk_artifact_version" ON "server_app_artifact_version" ("artifact_id", "version");

-- Table: derisk_serve_cron_job
CREATE TABLE IF NOT EXISTS "derisk_serve_cron_job" (
  "id" SERIAL,
  "name" VARCHAR(255) NOT NULL,
  "description" TEXT,
  "enabled" INTEGER DEFAULT true,
  "delete_after_run" INTEGER DEFAULT false,
  "schedule_kind" VARCHAR(32) NOT NULL,
  "schedule_at" VARCHAR(64),
  "schedule_every_ms" INTEGER,
  "schedule_anchor_ms" INTEGER,
  "schedule_expr" VARCHAR(128),
  "schedule_tz" VARCHAR(64),
  "payload_kind" VARCHAR(32) NOT NULL,
  "payload_data" JSON,
  "session_mode" VARCHAR(16) DEFAULT isolated,
  "conv_session_id" VARCHAR(64),
  "next_run_at_ms" INTEGER,
  "running_at_ms" INTEGER,
  "last_run_at_ms" INTEGER,
  "last_status" VARCHAR(32),
  "last_error" TEXT,
  "last_duration_ms" INTEGER,
  "consecutive_errors" INTEGER DEFAULT false,
  "created_by_user_id" VARCHAR(128),
  "gmt_create" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  "gmt_modified" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY ("id")
);

-- Table: derisk_serve_flow
CREATE TABLE IF NOT EXISTS "derisk_serve_flow" (
  "id" SERIAL,
  "uid" VARCHAR(128) NOT NULL,
  "dag_id" VARCHAR(128),
  "label_info" VARCHAR(128),
  "name" VARCHAR(128),
  "flow_category" VARCHAR(64),
  "flow_data" TEXT,
  "description" VARCHAR(512),
  "state" VARCHAR(32),
  "error_message" VARCHAR(512),
  "source" VARCHAR(64),
  "source_url" VARCHAR(512),
  "version" VARCHAR(32),
  "define_type" VARCHAR(32) DEFAULT json,
  "editable" INTEGER,
  "variables" TEXT,
  "user_name" VARCHAR(128),
  "sys_code" VARCHAR(128),
  "gmt_create" TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  "gmt_modified" TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY ("id"),
  CONSTRAINT "uk_uid" UNIQUE ("uid")
);
CREATE INDEX "ix_derisk_serve_flow_dag_id" ON "derisk_serve_flow" ("dag_id");
CREATE INDEX "ix_derisk_serve_flow_sys_code" ON "derisk_serve_flow" ("sys_code");
CREATE INDEX "ix_derisk_serve_flow_name" ON "derisk_serve_flow" ("name");
CREATE INDEX "ix_derisk_serve_flow_uid" ON "derisk_serve_flow" ("uid");
CREATE INDEX "ix_derisk_serve_flow_user_name" ON "derisk_serve_flow" ("user_name");

-- Table: derisk_serve_variables
CREATE TABLE IF NOT EXISTS "derisk_serve_variables" (
  "id" SERIAL,
  "key_info" VARCHAR(128) NOT NULL,
  "name" VARCHAR(128),
  "label_info" VARCHAR(128),
  "value" TEXT,
  "value_type" VARCHAR(32),
  "category" VARCHAR(32) DEFAULT common,
  "encryption_method" VARCHAR(32),
  "salt" VARCHAR(128),
  "scope" VARCHAR(32) DEFAULT global,
  "scope_key" VARCHAR(256),
  "enabled" INTEGER DEFAULT true,
  "description" TEXT,
  "user_name" VARCHAR(128),
  "sys_code" VARCHAR(128),
  "gmt_create" TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  "gmt_modified" TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY ("id")
);
CREATE INDEX "ix_derisk_serve_variables_name" ON "derisk_serve_variables" ("name");
CREATE INDEX "ix_derisk_serve_variables_user_name" ON "derisk_serve_variables" ("user_name");
CREATE INDEX "ix_derisk_serve_variables_key_info" ON "derisk_serve_variables" ("key_info");
CREATE INDEX "ix_derisk_serve_variables_sys_code" ON "derisk_serve_variables" ("sys_code");

-- Table: connect_config
CREATE TABLE IF NOT EXISTS "connect_config" (
  "id" SERIAL,
  "db_type" VARCHAR(255) NOT NULL,
  "db_name" VARCHAR(255) NOT NULL,
  "db_path" VARCHAR(255),
  "db_host" VARCHAR(255),
  "db_port" VARCHAR(255),
  "db_user" VARCHAR(255),
  "db_pwd" VARCHAR(255),
  "comment" TEXT,
  "sys_code" VARCHAR(128),
  "user_id" VARCHAR(128),
  "user_name" VARCHAR(128),
  "gmt_created" TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  "gmt_modified" TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  "ext_config" TEXT,
  "owner_workspace_id" INTEGER,
  PRIMARY KEY ("id"),
  CONSTRAINT "uk_db" UNIQUE ("db_name")
);
CREATE INDEX "ix_connect_config_user_name" ON "connect_config" ("user_name");
CREATE INDEX "idx_q_db_type" ON "connect_config" ("db_type");
CREATE INDEX "idx_q_owner_workspace" ON "connect_config" ("owner_workspace_id");
CREATE INDEX "ix_connect_config_sys_code" ON "connect_config" ("sys_code");
CREATE INDEX "ix_connect_config_user_id" ON "connect_config" ("user_id");

-- Table: db_spec
CREATE TABLE IF NOT EXISTS "db_spec" (
  "id" SERIAL,
  "datasource_id" INTEGER NOT NULL,
  "db_name" VARCHAR(255) NOT NULL,
  "db_type" VARCHAR(64) NOT NULL,
  "spec_content" TEXT NOT NULL,
  "table_count" INTEGER,
  "group_config" TEXT,
  "relations" TEXT,
  "status" VARCHAR(32) NOT NULL DEFAULT generating,
  "gmt_created" TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  "gmt_modified" TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY ("id"),
  CONSTRAINT "uk_db_spec_datasource" UNIQUE ("datasource_id")
);

-- Table: table_spec
CREATE TABLE IF NOT EXISTS "table_spec" (
  "id" SERIAL,
  "datasource_id" INTEGER NOT NULL,
  "table_name" VARCHAR(255) NOT NULL,
  "table_comment" TEXT,
  "row_count" INTEGER,
  "columns_json" TEXT NOT NULL,
  "indexes_json" TEXT,
  "sample_data_json" TEXT,
  "create_ddl" TEXT,
  "foreign_keys_json" TEXT,
  "group_name" VARCHAR(128),
  "gmt_created" TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  "gmt_modified" TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY ("id"),
  CONSTRAINT "uk_table_spec_ds_table" UNIQUE ("datasource_id", "table_name")
);
CREATE INDEX "idx_table_spec_ds" ON "table_spec" ("datasource_id");

-- ============================================================
-- End of DDL Script
-- ============================================================