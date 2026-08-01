-- ============================================================
-- PostgreSQL Incremental DDL Script for Derisk
-- Upgrade from 0.3.0 to 0.3.0
-- Source schema generated: 2026-07-30T22:57:45.622429
-- Generated: 2026-07-30T22:57:45.623393
-- ============================================================

-- ============================================================
-- Modified Tables
-- ============================================================

-- Table: chat_history
ALTER TABLE "chat_history" ADD COLUMN "id" SERIAL;
ALTER TABLE "chat_history" ADD COLUMN "workspace_id" INTEGER;
ALTER TABLE "chat_history" ADD COLUMN "gmt_create" TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE "chat_history" ADD COLUMN "message_ids" TEXT;
ALTER TABLE "chat_history" ADD COLUMN "gmt_modified" TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE "chat_history" ADD COLUMN "conv_uid" VARCHAR(255) NOT NULL;
ALTER TABLE "chat_history" ADD COLUMN "app_code" VARCHAR(255);
ALTER TABLE "chat_history" ADD COLUMN "sys_code" VARCHAR(128);
ALTER TABLE "chat_history" ADD COLUMN "task_id" INTEGER;
ALTER TABLE "chat_history" ADD COLUMN "messages" TEXT;
ALTER TABLE "chat_history" ADD COLUMN "summary" TEXT NOT NULL;
ALTER TABLE "chat_history" ADD COLUMN "chat_mode" VARCHAR(255) NOT NULL;
ALTER TABLE "chat_history" ADD COLUMN "user_name" VARCHAR(255);
CREATE INDEX "ix_chat_history_task_id" ON "chat_history" ("task_id");
CREATE INDEX "ix_chat_history_workspace_id" ON "chat_history" ("workspace_id");
CREATE INDEX "ix_chat_history_sys_code" ON "chat_history" ("sys_code");
ALTER TABLE "chat_history" ADD CONSTRAINT "uk_conv_uid" UNIQUE ("conv_uid");

-- Table: chat_history_message
ALTER TABLE "chat_history_message" ADD COLUMN "round_index" INTEGER NOT NULL;
ALTER TABLE "chat_history_message" ADD COLUMN "id" SERIAL;
ALTER TABLE "chat_history_message" ADD COLUMN "gmt_create" TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE "chat_history_message" ADD COLUMN "gmt_modified" TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE "chat_history_message" ADD COLUMN "message_detail" TEXT;
ALTER TABLE "chat_history_message" ADD COLUMN "conv_uid" VARCHAR(255) NOT NULL;
ALTER TABLE "chat_history_message" ADD COLUMN "index" INTEGER NOT NULL;
ALTER TABLE "chat_history_message" ADD CONSTRAINT "uk_conversation_message" UNIQUE ("conv_uid", "index");

-- Table: connect_config
ALTER TABLE "connect_config" ADD COLUMN "db_type" VARCHAR(255) NOT NULL;
ALTER TABLE "connect_config" ADD COLUMN "id" SERIAL;
ALTER TABLE "connect_config" ADD COLUMN "db_pwd" VARCHAR(255);
ALTER TABLE "connect_config" ADD COLUMN "db_user" VARCHAR(255);
ALTER TABLE "connect_config" ADD COLUMN "gmt_modified" TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE "connect_config" ADD COLUMN "db_name" VARCHAR(255) NOT NULL;
ALTER TABLE "connect_config" ADD COLUMN "db_host" VARCHAR(255);
ALTER TABLE "connect_config" ADD COLUMN "db_port" VARCHAR(255);
ALTER TABLE "connect_config" ADD COLUMN "comment" TEXT;
ALTER TABLE "connect_config" ADD COLUMN "user_name" VARCHAR(128);
ALTER TABLE "connect_config" ADD COLUMN "user_id" VARCHAR(128);
ALTER TABLE "connect_config" ADD COLUMN "ext_config" TEXT;
ALTER TABLE "connect_config" ADD COLUMN "sys_code" VARCHAR(128);
ALTER TABLE "connect_config" ADD COLUMN "gmt_created" TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE "connect_config" ADD COLUMN "db_path" VARCHAR(255);
CREATE INDEX "ix_connect_config_user_name" ON "connect_config" ("user_name");
CREATE INDEX "ix_connect_config_user_id" ON "connect_config" ("user_id");
CREATE INDEX "idx_q_db_type" ON "connect_config" ("db_type");
CREATE INDEX "ix_connect_config_sys_code" ON "connect_config" ("sys_code");
ALTER TABLE "connect_config" ADD CONSTRAINT "uk_db" UNIQUE ("db_name");

-- Table: db_spec
ALTER TABLE "db_spec" ADD COLUMN "spec_content" TEXT NOT NULL;
ALTER TABLE "db_spec" ADD COLUMN "id" SERIAL;
ALTER TABLE "db_spec" ADD COLUMN "db_type" VARCHAR(64) NOT NULL;
ALTER TABLE "db_spec" ADD COLUMN "gmt_modified" TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE "db_spec" ADD COLUMN "db_name" VARCHAR(255) NOT NULL;
ALTER TABLE "db_spec" ADD COLUMN "group_config" TEXT;
ALTER TABLE "db_spec" ADD COLUMN "status" VARCHAR(32) NOT NULL DEFAULT generating;
ALTER TABLE "db_spec" ADD COLUMN "datasource_id" INTEGER NOT NULL;
ALTER TABLE "db_spec" ADD COLUMN "gmt_created" TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE "db_spec" ADD COLUMN "relations" TEXT;
ALTER TABLE "db_spec" ADD COLUMN "table_count" INTEGER;
ALTER TABLE "db_spec" ADD CONSTRAINT "uk_db_spec_datasource" UNIQUE ("datasource_id");

-- Table: derisk_serve_cron_job
ALTER TABLE "derisk_serve_cron_job" ADD COLUMN "running_at_ms" INTEGER;
ALTER TABLE "derisk_serve_cron_job" ADD COLUMN "schedule_at" VARCHAR(64);
ALTER TABLE "derisk_serve_cron_job" ADD COLUMN "gmt_modified" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE "derisk_serve_cron_job" ADD COLUMN "schedule_anchor_ms" INTEGER;
ALTER TABLE "derisk_serve_cron_job" ADD COLUMN "schedule_expr" VARCHAR(128);
ALTER TABLE "derisk_serve_cron_job" ADD COLUMN "consecutive_errors" INTEGER DEFAULT false;
ALTER TABLE "derisk_serve_cron_job" ADD COLUMN "schedule_every_ms" INTEGER;
ALTER TABLE "derisk_serve_cron_job" ADD COLUMN "schedule_tz" VARCHAR(64);
ALTER TABLE "derisk_serve_cron_job" ADD COLUMN "description" TEXT;
ALTER TABLE "derisk_serve_cron_job" ADD COLUMN "session_mode" VARCHAR(16) DEFAULT isolated;
ALTER TABLE "derisk_serve_cron_job" ADD COLUMN "last_run_at_ms" INTEGER;
ALTER TABLE "derisk_serve_cron_job" ADD COLUMN "next_run_at_ms" INTEGER;
ALTER TABLE "derisk_serve_cron_job" ADD COLUMN "name" VARCHAR(255) NOT NULL;
ALTER TABLE "derisk_serve_cron_job" ADD COLUMN "id" SERIAL;
ALTER TABLE "derisk_serve_cron_job" ADD COLUMN "gmt_create" TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE "derisk_serve_cron_job" ADD COLUMN "last_error" TEXT;
ALTER TABLE "derisk_serve_cron_job" ADD COLUMN "schedule_kind" VARCHAR(32) NOT NULL;
ALTER TABLE "derisk_serve_cron_job" ADD COLUMN "conv_session_id" VARCHAR(64);
ALTER TABLE "derisk_serve_cron_job" ADD COLUMN "enabled" INTEGER DEFAULT true;
ALTER TABLE "derisk_serve_cron_job" ADD COLUMN "payload_kind" VARCHAR(32) NOT NULL;
ALTER TABLE "derisk_serve_cron_job" ADD COLUMN "payload_data" JSON;
ALTER TABLE "derisk_serve_cron_job" ADD COLUMN "last_status" VARCHAR(32);
ALTER TABLE "derisk_serve_cron_job" ADD COLUMN "last_duration_ms" INTEGER;
ALTER TABLE "derisk_serve_cron_job" ADD COLUMN "delete_after_run" INTEGER DEFAULT false;
ALTER TABLE "derisk_serve_cron_job" ADD COLUMN "created_by_user_id" VARCHAR(128);

-- Table: derisk_serve_flow
ALTER TABLE "derisk_serve_flow" ADD COLUMN "editable" INTEGER;
ALTER TABLE "derisk_serve_flow" ADD COLUMN "uid" VARCHAR(128) NOT NULL;
ALTER TABLE "derisk_serve_flow" ADD COLUMN "flow_category" VARCHAR(64);
ALTER TABLE "derisk_serve_flow" ADD COLUMN "gmt_modified" TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE "derisk_serve_flow" ADD COLUMN "state" VARCHAR(32);
ALTER TABLE "derisk_serve_flow" ADD COLUMN "source_url" VARCHAR(512);
ALTER TABLE "derisk_serve_flow" ADD COLUMN "source" VARCHAR(64);
ALTER TABLE "derisk_serve_flow" ADD COLUMN "flow_data" TEXT;
ALTER TABLE "derisk_serve_flow" ADD COLUMN "sys_code" VARCHAR(128);
ALTER TABLE "derisk_serve_flow" ADD COLUMN "dag_id" VARCHAR(128);
ALTER TABLE "derisk_serve_flow" ADD COLUMN "description" VARCHAR(512);
ALTER TABLE "derisk_serve_flow" ADD COLUMN "user_name" VARCHAR(128);
ALTER TABLE "derisk_serve_flow" ADD COLUMN "name" VARCHAR(128);
ALTER TABLE "derisk_serve_flow" ADD COLUMN "id" SERIAL;
ALTER TABLE "derisk_serve_flow" ADD COLUMN "gmt_create" TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE "derisk_serve_flow" ADD COLUMN "variables" TEXT;
ALTER TABLE "derisk_serve_flow" ADD COLUMN "error_message" VARCHAR(512);
ALTER TABLE "derisk_serve_flow" ADD COLUMN "label_info" VARCHAR(128);
ALTER TABLE "derisk_serve_flow" ADD COLUMN "define_type" VARCHAR(32) DEFAULT json;
ALTER TABLE "derisk_serve_flow" ADD COLUMN "version" VARCHAR(32);
CREATE INDEX "ix_derisk_serve_flow_sys_code" ON "derisk_serve_flow" ("sys_code");
CREATE INDEX "ix_derisk_serve_flow_user_name" ON "derisk_serve_flow" ("user_name");
CREATE INDEX "ix_derisk_serve_flow_dag_id" ON "derisk_serve_flow" ("dag_id");
CREATE INDEX "ix_derisk_serve_flow_uid" ON "derisk_serve_flow" ("uid");
CREATE INDEX "ix_derisk_serve_flow_name" ON "derisk_serve_flow" ("name");
ALTER TABLE "derisk_serve_flow" ADD CONSTRAINT "uk_uid" UNIQUE ("uid");

-- Table: derisk_serve_variables
ALTER TABLE "derisk_serve_variables" ADD COLUMN "gmt_modified" TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE "derisk_serve_variables" ADD COLUMN "value_type" VARCHAR(32);
ALTER TABLE "derisk_serve_variables" ADD COLUMN "category" VARCHAR(32) DEFAULT common;
ALTER TABLE "derisk_serve_variables" ADD COLUMN "sys_code" VARCHAR(128);
ALTER TABLE "derisk_serve_variables" ADD COLUMN "description" TEXT;
ALTER TABLE "derisk_serve_variables" ADD COLUMN "value" TEXT;
ALTER TABLE "derisk_serve_variables" ADD COLUMN "user_name" VARCHAR(128);
ALTER TABLE "derisk_serve_variables" ADD COLUMN "id" SERIAL;
ALTER TABLE "derisk_serve_variables" ADD COLUMN "name" VARCHAR(128);
ALTER TABLE "derisk_serve_variables" ADD COLUMN "encryption_method" VARCHAR(32);
ALTER TABLE "derisk_serve_variables" ADD COLUMN "gmt_create" TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE "derisk_serve_variables" ADD COLUMN "enabled" INTEGER DEFAULT true;
ALTER TABLE "derisk_serve_variables" ADD COLUMN "salt" VARCHAR(128);
ALTER TABLE "derisk_serve_variables" ADD COLUMN "scope_key" VARCHAR(256);
ALTER TABLE "derisk_serve_variables" ADD COLUMN "label_info" VARCHAR(128);
ALTER TABLE "derisk_serve_variables" ADD COLUMN "scope" VARCHAR(32) DEFAULT global;
ALTER TABLE "derisk_serve_variables" ADD COLUMN "key_info" VARCHAR(128) NOT NULL;
CREATE INDEX "ix_derisk_serve_variables_key_info" ON "derisk_serve_variables" ("key_info");
CREATE INDEX "ix_derisk_serve_variables_user_name" ON "derisk_serve_variables" ("user_name");
CREATE INDEX "ix_derisk_serve_variables_name" ON "derisk_serve_variables" ("name");
CREATE INDEX "ix_derisk_serve_variables_sys_code" ON "derisk_serve_variables" ("sys_code");

-- Table: server_app_artifact
ALTER TABLE "server_app_artifact" ADD COLUMN "type" VARCHAR(32) NOT NULL;
ALTER TABLE "server_app_artifact" ADD COLUMN "id" SERIAL;
ALTER TABLE "server_app_artifact" ADD COLUMN "workspace_id" INTEGER NOT NULL;
ALTER TABLE "server_app_artifact" ADD COLUMN "provenance_json" TEXT;
ALTER TABLE "server_app_artifact" ADD COLUMN "content_ref" VARCHAR(512);
ALTER TABLE "server_app_artifact" ADD COLUMN "gmt_create" TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE "server_app_artifact" ADD COLUMN "gmt_modified" TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE "server_app_artifact" ADD COLUMN "title" VARCHAR(256) NOT NULL;
ALTER TABLE "server_app_artifact" ADD COLUMN "created_by_user" INTEGER;
ALTER TABLE "server_app_artifact" ADD COLUMN "created_by_agent" VARCHAR(128);
ALTER TABLE "server_app_artifact" ADD COLUMN "content_text" TEXT;
ALTER TABLE "server_app_artifact" ADD COLUMN "task_id" INTEGER NOT NULL;
ALTER TABLE "server_app_artifact" ADD COLUMN "is_shared" BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE "server_app_artifact" ADD COLUMN "current_version" INTEGER NOT NULL DEFAULT true;
CREATE INDEX "ix_server_app_artifact_workspace_id" ON "server_app_artifact" ("workspace_id");
CREATE INDEX "ix_server_app_artifact_task_id" ON "server_app_artifact" ("task_id");

-- Table: server_app_artifact_version
ALTER TABLE "server_app_artifact_version" ADD COLUMN "id" SERIAL;
ALTER TABLE "server_app_artifact_version" ADD COLUMN "version" INTEGER NOT NULL;
ALTER TABLE "server_app_artifact_version" ADD COLUMN "artifact_id" INTEGER NOT NULL;
ALTER TABLE "server_app_artifact_version" ADD COLUMN "content_ref" VARCHAR(512);
ALTER TABLE "server_app_artifact_version" ADD COLUMN "gmt_create" TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE "server_app_artifact_version" ADD COLUMN "diff_summary" TEXT;
ALTER TABLE "server_app_artifact_version" ADD COLUMN "created_by" VARCHAR(128);
CREATE INDEX "ix_server_app_artifact_version_artifact_id" ON "server_app_artifact_version" ("artifact_id");
CREATE UNIQUE INDEX "uk_artifact_version" ON "server_app_artifact_version" ("artifact_id", "version");

-- Table: table_spec
ALTER TABLE "table_spec" ADD COLUMN "columns_json" TEXT NOT NULL;
ALTER TABLE "table_spec" ADD COLUMN "id" SERIAL;
ALTER TABLE "table_spec" ADD COLUMN "indexes_json" TEXT;
ALTER TABLE "table_spec" ADD COLUMN "table_name" VARCHAR(255) NOT NULL;
ALTER TABLE "table_spec" ADD COLUMN "sample_data_json" TEXT;
ALTER TABLE "table_spec" ADD COLUMN "gmt_modified" TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE "table_spec" ADD COLUMN "create_ddl" TEXT;
ALTER TABLE "table_spec" ADD COLUMN "table_comment" TEXT;
ALTER TABLE "table_spec" ADD COLUMN "group_name" VARCHAR(128);
ALTER TABLE "table_spec" ADD COLUMN "foreign_keys_json" TEXT;
ALTER TABLE "table_spec" ADD COLUMN "datasource_id" INTEGER NOT NULL;
ALTER TABLE "table_spec" ADD COLUMN "row_count" INTEGER;
ALTER TABLE "table_spec" ADD COLUMN "gmt_created" TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
CREATE INDEX "idx_table_spec_ds" ON "table_spec" ("datasource_id");
ALTER TABLE "table_spec" ADD CONSTRAINT "uk_table_spec_ds_table" UNIQUE ("datasource_id", "table_name");

-- ============================================================
-- End of Incremental DDL Script
-- ============================================================