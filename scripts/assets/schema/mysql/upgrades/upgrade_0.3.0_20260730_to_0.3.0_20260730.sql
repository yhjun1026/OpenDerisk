-- ============================================================
-- MySQL Incremental DDL Script for Derisk
-- Upgrade from 0.3.0 to 0.3.0
-- Source schema generated: 2026-07-30T23:04:03.999214
-- Generated: 2026-07-30T23:04:04.000656
-- ============================================================

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- ============================================================
-- Modified Tables
-- ============================================================

-- Table: chat_history
ALTER TABLE `chat_history` ADD COLUMN `message_ids` LONGTEXT NULL COMMENT 'Message ids, split by comma';
ALTER TABLE `chat_history` ADD COLUMN `gmt_modified` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Record update time';
ALTER TABLE `chat_history` ADD COLUMN `conv_uid` VARCHAR(255) NOT NULL COMMENT 'Conversation record unique id';
ALTER TABLE `chat_history` ADD COLUMN `id` INT NOT NULL AUTO_INCREMENT COMMENT 'autoincrement id';
ALTER TABLE `chat_history` ADD COLUMN `workspace_id` INT NULL COMMENT 'Workspace id, NULL for HomeChat';
ALTER TABLE `chat_history` ADD COLUMN `task_id` INT NULL COMMENT 'Task id this conversation belongs to';
ALTER TABLE `chat_history` ADD COLUMN `messages` LONGTEXT NULL COMMENT 'Conversation details';
ALTER TABLE `chat_history` ADD COLUMN `app_code` VARCHAR(255) NULL COMMENT 'App unique code';
ALTER TABLE `chat_history` ADD COLUMN `chat_mode` VARCHAR(255) NOT NULL COMMENT 'Conversation scene mode';
ALTER TABLE `chat_history` ADD COLUMN `gmt_create` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Record creation time';
ALTER TABLE `chat_history` ADD COLUMN `summary` LONGTEXT NOT NULL COMMENT 'Conversation record summary';
ALTER TABLE `chat_history` ADD COLUMN `user_name` VARCHAR(255) NULL COMMENT 'interlocutor';
ALTER TABLE `chat_history` ADD COLUMN `sys_code` VARCHAR(128) NULL COMMENT 'System code';
ALTER TABLE `chat_history` ADD INDEX `ix_chat_history_workspace_id` (`workspace_id`);
ALTER TABLE `chat_history` ADD INDEX `ix_chat_history_sys_code` (`sys_code`);
ALTER TABLE `chat_history` ADD INDEX `ix_chat_history_task_id` (`task_id`);
ALTER TABLE `chat_history` ADD CONSTRAINT `uk_conv_uid` UNIQUE (`conv_uid`);

-- Table: chat_history_message
ALTER TABLE `chat_history_message` ADD COLUMN `index` INT NOT NULL COMMENT 'Message index';
ALTER TABLE `chat_history_message` ADD COLUMN `message_detail` LONGTEXT NULL COMMENT 'Message details, json format';
ALTER TABLE `chat_history_message` ADD COLUMN `round_index` INT NOT NULL COMMENT 'Message round index';
ALTER TABLE `chat_history_message` ADD COLUMN `gmt_create` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Record creation time';
ALTER TABLE `chat_history_message` ADD COLUMN `gmt_modified` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Record update time';
ALTER TABLE `chat_history_message` ADD COLUMN `conv_uid` VARCHAR(255) NOT NULL COMMENT 'Conversation record unique id';
ALTER TABLE `chat_history_message` ADD COLUMN `id` INT NOT NULL AUTO_INCREMENT COMMENT 'autoincrement id';
ALTER TABLE `chat_history_message` ADD CONSTRAINT `uk_conversation_message` UNIQUE (`conv_uid`, `index`);

-- Table: connect_config
ALTER TABLE `connect_config` ADD COLUMN `db_path` VARCHAR(255) NULL COMMENT 'file db path';
ALTER TABLE `connect_config` ADD COLUMN `gmt_modified` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Record update time';
ALTER TABLE `connect_config` ADD COLUMN `comment` TEXT NULL COMMENT 'db comment';
ALTER TABLE `connect_config` ADD COLUMN `id` INT NOT NULL AUTO_INCREMENT COMMENT 'autoincrement id';
ALTER TABLE `connect_config` ADD COLUMN `db_host` VARCHAR(255) NULL COMMENT 'db connect host(not file db)';
ALTER TABLE `connect_config` ADD COLUMN `user_id` VARCHAR(128) NULL COMMENT 'User id';
ALTER TABLE `connect_config` ADD COLUMN `ext_config` TEXT NULL COMMENT 'Extended configuration, json format';
ALTER TABLE `connect_config` ADD COLUMN `db_type` VARCHAR(255) NOT NULL COMMENT 'db type';
ALTER TABLE `connect_config` ADD COLUMN `db_pwd` VARCHAR(255) NULL COMMENT 'db password';
ALTER TABLE `connect_config` ADD COLUMN `db_name` VARCHAR(255) NOT NULL COMMENT 'db name';
ALTER TABLE `connect_config` ADD COLUMN `user_name` VARCHAR(128) NULL COMMENT 'User name';
ALTER TABLE `connect_config` ADD COLUMN `db_user` VARCHAR(255) NULL COMMENT 'db user';
ALTER TABLE `connect_config` ADD COLUMN `db_port` VARCHAR(255) NULL COMMENT 'db connect port(not file db)';
ALTER TABLE `connect_config` ADD COLUMN `gmt_created` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Record creation time';
ALTER TABLE `connect_config` ADD COLUMN `sys_code` VARCHAR(128) NULL COMMENT 'System code';
ALTER TABLE `connect_config` ADD INDEX `ix_connect_config_user_name` (`user_name`);
ALTER TABLE `connect_config` ADD INDEX `idx_q_db_type` (`db_type`);
ALTER TABLE `connect_config` ADD INDEX `ix_connect_config_user_id` (`user_id`);
ALTER TABLE `connect_config` ADD INDEX `ix_connect_config_sys_code` (`sys_code`);
ALTER TABLE `connect_config` ADD CONSTRAINT `uk_db` UNIQUE (`db_name`);

-- Table: db_spec
ALTER TABLE `db_spec` ADD COLUMN `table_count` INT NULL COMMENT 'Total number of tables';
ALTER TABLE `db_spec` ADD COLUMN `gmt_modified` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Record update time';
ALTER TABLE `db_spec` ADD COLUMN `status` VARCHAR(32) NOT NULL DEFAULT generating COMMENT 'Status: ready, generating, failed';
ALTER TABLE `db_spec` ADD COLUMN `id` INT NOT NULL AUTO_INCREMENT COMMENT 'autoincrement id';
ALTER TABLE `db_spec` ADD COLUMN `spec_content` TEXT NOT NULL COMMENT 'JSON: table list index with summaries';
ALTER TABLE `db_spec` ADD COLUMN `group_config` TEXT NULL COMMENT 'JSON: table grouping configuration';
ALTER TABLE `db_spec` ADD COLUMN `db_type` VARCHAR(64) NOT NULL COMMENT 'Database type';
ALTER TABLE `db_spec` ADD COLUMN `datasource_id` INT NOT NULL COMMENT 'FK to connect_config.id';
ALTER TABLE `db_spec` ADD COLUMN `db_name` VARCHAR(255) NOT NULL COMMENT 'Database name';
ALTER TABLE `db_spec` ADD COLUMN `relations` TEXT NULL COMMENT 'JSON: detected table relationships';
ALTER TABLE `db_spec` ADD COLUMN `gmt_created` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Record creation time';
ALTER TABLE `db_spec` ADD CONSTRAINT `uk_db_spec_datasource` UNIQUE (`datasource_id`);

-- Table: derisk_serve_cron_job
ALTER TABLE `derisk_serve_cron_job` ADD COLUMN `next_run_at_ms` INT NULL COMMENT 'Next run time in ms';
ALTER TABLE `derisk_serve_cron_job` ADD COLUMN `created_by_user_id` VARCHAR(128) NULL COMMENT 'Job creator user id';
ALTER TABLE `derisk_serve_cron_job` ADD COLUMN `last_run_at_ms` INT NULL COMMENT 'Last run time in ms';
ALTER TABLE `derisk_serve_cron_job` ADD COLUMN `gmt_modified` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Record update time';
ALTER TABLE `derisk_serve_cron_job` ADD COLUMN `conv_session_id` VARCHAR(64) NULL COMMENT 'Conversation session ID for shared sessions';
ALTER TABLE `derisk_serve_cron_job` ADD COLUMN `last_duration_ms` INT NULL COMMENT 'Last run duration in ms';
ALTER TABLE `derisk_serve_cron_job` ADD COLUMN `schedule_at` VARCHAR(64) NULL COMMENT 'ISO datetime for ''at'' schedule';
ALTER TABLE `derisk_serve_cron_job` ADD COLUMN `gmt_create` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Record creation time';
ALTER TABLE `derisk_serve_cron_job` ADD COLUMN `consecutive_errors` INT NULL DEFAULT 0 COMMENT 'Consecutive error count';
ALTER TABLE `derisk_serve_cron_job` ADD COLUMN `name` VARCHAR(255) NOT NULL COMMENT 'Job name';
ALTER TABLE `derisk_serve_cron_job` ADD COLUMN `schedule_tz` VARCHAR(64) NULL COMMENT 'Timezone';
ALTER TABLE `derisk_serve_cron_job` ADD COLUMN `schedule_expr` VARCHAR(128) NULL COMMENT 'Cron expression for ''cron'' schedule';
ALTER TABLE `derisk_serve_cron_job` ADD COLUMN `enabled` INT NULL DEFAULT 1 COMMENT 'Whether job is enabled (1=yes, 0=no)';
ALTER TABLE `derisk_serve_cron_job` ADD COLUMN `description` TEXT NULL COMMENT 'Job description';
ALTER TABLE `derisk_serve_cron_job` ADD COLUMN `session_mode` VARCHAR(16) NULL DEFAULT isolated COMMENT 'Session mode (isolated/shared)';
ALTER TABLE `derisk_serve_cron_job` ADD COLUMN `id` VARCHAR(64) NOT NULL AUTO_INCREMENT COMMENT 'Job unique identifier';
ALTER TABLE `derisk_serve_cron_job` ADD COLUMN `payload_data` JSON NULL COMMENT 'Payload data as JSON';
ALTER TABLE `derisk_serve_cron_job` ADD COLUMN `schedule_every_ms` INT NULL COMMENT 'Interval in ms for ''every'' schedule';
ALTER TABLE `derisk_serve_cron_job` ADD COLUMN `delete_after_run` INT NULL DEFAULT 0 COMMENT 'Delete after run (1=yes, 0=no)';
ALTER TABLE `derisk_serve_cron_job` ADD COLUMN `last_status` VARCHAR(32) NULL COMMENT 'Last run status (ok/error/skipped)';
ALTER TABLE `derisk_serve_cron_job` ADD COLUMN `payload_kind` VARCHAR(32) NOT NULL COMMENT 'Payload kind (agentTurn/toolCall/systemEvent)';
ALTER TABLE `derisk_serve_cron_job` ADD COLUMN `schedule_kind` VARCHAR(32) NOT NULL COMMENT 'Schedule kind (at/every/cron)';
ALTER TABLE `derisk_serve_cron_job` ADD COLUMN `running_at_ms` INT NULL COMMENT 'Current run start time in ms';
ALTER TABLE `derisk_serve_cron_job` ADD COLUMN `last_error` TEXT NULL COMMENT 'Last error message';
ALTER TABLE `derisk_serve_cron_job` ADD COLUMN `schedule_anchor_ms` INT NULL COMMENT 'Anchor time for ''every'' schedule';

-- Table: derisk_serve_flow
ALTER TABLE `derisk_serve_flow` ADD COLUMN `gmt_modified` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Record update time';
ALTER TABLE `derisk_serve_flow` ADD COLUMN `gmt_create` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Record creation time';
ALTER TABLE `derisk_serve_flow` ADD COLUMN `description` VARCHAR(512) NULL COMMENT 'Flow description';
ALTER TABLE `derisk_serve_flow` ADD COLUMN `variables` TEXT NULL COMMENT 'Flow variables, JSON format';
ALTER TABLE `derisk_serve_flow` ADD COLUMN `flow_category` VARCHAR(64) NULL COMMENT 'Flow category';
ALTER TABLE `derisk_serve_flow` ADD COLUMN `id` INT NOT NULL AUTO_INCREMENT COMMENT 'Auto increment id';
ALTER TABLE `derisk_serve_flow` ADD COLUMN `source_url` VARCHAR(512) NULL COMMENT 'Flow source url';
ALTER TABLE `derisk_serve_flow` ADD COLUMN `state` VARCHAR(32) NULL COMMENT 'Flow state';
ALTER TABLE `derisk_serve_flow` ADD COLUMN `dag_id` VARCHAR(128) NULL COMMENT 'DAG id';
ALTER TABLE `derisk_serve_flow` ADD COLUMN `user_name` VARCHAR(128) NULL COMMENT 'User name';
ALTER TABLE `derisk_serve_flow` ADD COLUMN `error_message` VARCHAR(512) NULL COMMENT 'Error message';
ALTER TABLE `derisk_serve_flow` ADD COLUMN `flow_data` TEXT NULL COMMENT 'Flow data, JSON format';
ALTER TABLE `derisk_serve_flow` ADD COLUMN `editable` INT NULL COMMENT 'Editable, 0: editable, 1: not editable';
ALTER TABLE `derisk_serve_flow` ADD COLUMN `version` VARCHAR(32) NULL COMMENT 'Flow version';
ALTER TABLE `derisk_serve_flow` ADD COLUMN `uid` VARCHAR(128) NOT NULL COMMENT 'Unique id';
ALTER TABLE `derisk_serve_flow` ADD COLUMN `define_type` VARCHAR(32) NULL DEFAULT json COMMENT 'Flow define type(json or python)';
ALTER TABLE `derisk_serve_flow` ADD COLUMN `name` VARCHAR(128) NULL COMMENT 'Flow name';
ALTER TABLE `derisk_serve_flow` ADD COLUMN `label_info` VARCHAR(128) NULL COMMENT 'Flow label';
ALTER TABLE `derisk_serve_flow` ADD COLUMN `source` VARCHAR(64) NULL COMMENT 'Flow source';
ALTER TABLE `derisk_serve_flow` ADD COLUMN `sys_code` VARCHAR(128) NULL COMMENT 'System code';
ALTER TABLE `derisk_serve_flow` ADD INDEX `ix_derisk_serve_flow_user_name` (`user_name`);
ALTER TABLE `derisk_serve_flow` ADD INDEX `ix_derisk_serve_flow_name` (`name`);
ALTER TABLE `derisk_serve_flow` ADD INDEX `ix_derisk_serve_flow_sys_code` (`sys_code`);
ALTER TABLE `derisk_serve_flow` ADD INDEX `ix_derisk_serve_flow_dag_id` (`dag_id`);
ALTER TABLE `derisk_serve_flow` ADD INDEX `ix_derisk_serve_flow_uid` (`uid`);
ALTER TABLE `derisk_serve_flow` ADD CONSTRAINT `uk_uid` UNIQUE (`uid`);

-- Table: derisk_serve_variables
ALTER TABLE `derisk_serve_variables` ADD COLUMN `gmt_modified` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Record update time';
ALTER TABLE `derisk_serve_variables` ADD COLUMN `salt` VARCHAR(128) NULL COMMENT 'Variable salt';
ALTER TABLE `derisk_serve_variables` ADD COLUMN `gmt_create` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Record creation time';
ALTER TABLE `derisk_serve_variables` ADD COLUMN `name` VARCHAR(128) NULL COMMENT 'Variable name';
ALTER TABLE `derisk_serve_variables` ADD COLUMN `enabled` INT NULL DEFAULT 1 COMMENT 'Variable enabled, 0: disabled, 1: enabled';
ALTER TABLE `derisk_serve_variables` ADD COLUMN `description` TEXT NULL COMMENT 'Variable description';
ALTER TABLE `derisk_serve_variables` ADD COLUMN `value_type` VARCHAR(32) NULL COMMENT 'Variable value type(string, int, float, bool)';
ALTER TABLE `derisk_serve_variables` ADD COLUMN `value` TEXT NULL COMMENT 'Variable value, JSON format';
ALTER TABLE `derisk_serve_variables` ADD COLUMN `encryption_method` VARCHAR(32) NULL COMMENT 'Variable encryption method(fernet, simple, rsa, aes)';
ALTER TABLE `derisk_serve_variables` ADD COLUMN `id` INT NOT NULL AUTO_INCREMENT COMMENT 'Auto increment id';
ALTER TABLE `derisk_serve_variables` ADD COLUMN `scope_key` VARCHAR(256) NULL COMMENT 'Variable scope key, default is empty, for scope is ''flow_priv'', the scope_key is dag id of flow';
ALTER TABLE `derisk_serve_variables` ADD COLUMN `key_info` VARCHAR(128) NOT NULL COMMENT 'Variable key';
ALTER TABLE `derisk_serve_variables` ADD COLUMN `user_name` VARCHAR(128) NULL COMMENT 'User name';
ALTER TABLE `derisk_serve_variables` ADD COLUMN `label_info` VARCHAR(128) NULL COMMENT 'Variable label';
ALTER TABLE `derisk_serve_variables` ADD COLUMN `scope` VARCHAR(32) NULL DEFAULT global COMMENT 'Variable scope(global,flow,app,agent,datasource,flow_priv,agent_priv, etc)';
ALTER TABLE `derisk_serve_variables` ADD COLUMN `category` VARCHAR(32) NULL DEFAULT common COMMENT 'Variable category(common or secret)';
ALTER TABLE `derisk_serve_variables` ADD COLUMN `sys_code` VARCHAR(128) NULL COMMENT 'System code';
ALTER TABLE `derisk_serve_variables` ADD INDEX `ix_derisk_serve_variables_sys_code` (`sys_code`);
ALTER TABLE `derisk_serve_variables` ADD INDEX `ix_derisk_serve_variables_key_info` (`key_info`);
ALTER TABLE `derisk_serve_variables` ADD INDEX `ix_derisk_serve_variables_user_name` (`user_name`);
ALTER TABLE `derisk_serve_variables` ADD INDEX `ix_derisk_serve_variables_name` (`name`);

-- Table: server_app_artifact
ALTER TABLE `server_app_artifact` ADD COLUMN `content_ref` VARCHAR(512) NULL;
ALTER TABLE `server_app_artifact` ADD COLUMN `current_version` INT NOT NULL DEFAULT 1;
ALTER TABLE `server_app_artifact` ADD COLUMN `gmt_modified` DATETIME NULL DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE `server_app_artifact` ADD COLUMN `type` VARCHAR(32) NOT NULL;
ALTER TABLE `server_app_artifact` ADD COLUMN `is_shared` TINYINT(1) NOT NULL DEFAULT 0;
ALTER TABLE `server_app_artifact` ADD COLUMN `id` INT NOT NULL AUTO_INCREMENT;
ALTER TABLE `server_app_artifact` ADD COLUMN `task_id` INT NOT NULL;
ALTER TABLE `server_app_artifact` ADD COLUMN `workspace_id` INT NOT NULL;
ALTER TABLE `server_app_artifact` ADD COLUMN `provenance_json` TEXT NULL;
ALTER TABLE `server_app_artifact` ADD COLUMN `created_by_user` INT NULL;
ALTER TABLE `server_app_artifact` ADD COLUMN `content_text` TEXT NULL;
ALTER TABLE `server_app_artifact` ADD COLUMN `gmt_create` DATETIME NULL DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE `server_app_artifact` ADD COLUMN `created_by_agent` VARCHAR(128) NULL;
ALTER TABLE `server_app_artifact` ADD COLUMN `title` VARCHAR(256) NOT NULL;
ALTER TABLE `server_app_artifact` ADD INDEX `ix_server_app_artifact_workspace_id` (`workspace_id`);
ALTER TABLE `server_app_artifact` ADD INDEX `ix_server_app_artifact_task_id` (`task_id`);

-- Table: server_app_artifact_version
ALTER TABLE `server_app_artifact_version` ADD COLUMN `artifact_id` INT NOT NULL;
ALTER TABLE `server_app_artifact_version` ADD COLUMN `content_ref` VARCHAR(512) NULL;
ALTER TABLE `server_app_artifact_version` ADD COLUMN `created_by` VARCHAR(128) NULL;
ALTER TABLE `server_app_artifact_version` ADD COLUMN `gmt_create` DATETIME NULL DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE `server_app_artifact_version` ADD COLUMN `version` INT NOT NULL;
ALTER TABLE `server_app_artifact_version` ADD COLUMN `id` INT NOT NULL AUTO_INCREMENT;
ALTER TABLE `server_app_artifact_version` ADD COLUMN `diff_summary` TEXT NULL;
ALTER TABLE `server_app_artifact_version` ADD UNIQUE INDEX `uk_artifact_version` (`artifact_id`, `version`);
ALTER TABLE `server_app_artifact_version` ADD INDEX `ix_server_app_artifact_version_artifact_id` (`artifact_id`);

-- Table: table_spec
ALTER TABLE `table_spec` ADD COLUMN `sample_data_json` TEXT NULL COMMENT 'JSON: sample rows from the table';
ALTER TABLE `table_spec` ADD COLUMN `gmt_modified` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Record update time';
ALTER TABLE `table_spec` ADD COLUMN `columns_json` TEXT NOT NULL COMMENT 'JSON: array of column definitions (name, type, nullable, default, comment, pk)';
ALTER TABLE `table_spec` ADD COLUMN `row_count` INT NULL COMMENT 'Approximate row count';
ALTER TABLE `table_spec` ADD COLUMN `id` INT NOT NULL AUTO_INCREMENT COMMENT 'autoincrement id';
ALTER TABLE `table_spec` ADD COLUMN `table_comment` TEXT NULL COMMENT 'Table comment/description';
ALTER TABLE `table_spec` ADD COLUMN `create_ddl` TEXT NULL COMMENT 'CREATE TABLE DDL statement';
ALTER TABLE `table_spec` ADD COLUMN `foreign_keys_json` TEXT NULL COMMENT 'JSON: array of foreign key definitions (constrained_columns, referred_table, referred_columns)';
ALTER TABLE `table_spec` ADD COLUMN `datasource_id` INT NOT NULL COMMENT 'FK to connect_config.id';
ALTER TABLE `table_spec` ADD COLUMN `table_name` VARCHAR(255) NOT NULL COMMENT 'Table name';
ALTER TABLE `table_spec` ADD COLUMN `indexes_json` TEXT NULL COMMENT 'JSON: array of index definitions (name, columns, unique)';
ALTER TABLE `table_spec` ADD COLUMN `group_name` VARCHAR(128) NULL COMMENT 'Table group name for categorization';
ALTER TABLE `table_spec` ADD COLUMN `gmt_created` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Record creation time';
ALTER TABLE `table_spec` ADD INDEX `idx_table_spec_ds` (`datasource_id`);
ALTER TABLE `table_spec` ADD CONSTRAINT `uk_table_spec_ds_table` UNIQUE (`datasource_id`, `table_name`);

SET FOREIGN_KEY_CHECKS = 1;

-- ============================================================
-- End of Incremental DDL Script
-- ============================================================