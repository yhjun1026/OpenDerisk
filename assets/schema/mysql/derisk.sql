-- ============================================================
-- MySQL DDL Script for Derisk
-- Version: 0.3.0
-- Generated: 2026-08-01T19:26:32.846357
-- ============================================================

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- Table: chat_history
CREATE TABLE IF NOT EXISTS `chat_history` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT 'autoincrement id',
  `conv_uid` VARCHAR(255) NOT NULL COMMENT 'Conversation record unique id',
  `chat_mode` VARCHAR(255) NOT NULL COMMENT 'Conversation scene mode',
  `summary` LONGTEXT NOT NULL COMMENT 'Conversation record summary',
  `user_name` VARCHAR(255) NULL COMMENT 'interlocutor',
  `messages` LONGTEXT NULL COMMENT 'Conversation details',
  `message_ids` LONGTEXT NULL COMMENT 'Message ids, split by comma',
  `sys_code` VARCHAR(128) NULL COMMENT 'System code',
  `gmt_create` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Record creation time',
  `gmt_modified` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Record update time',
  `app_code` VARCHAR(255) NULL COMMENT 'App unique code',
  `workspace_id` INT NULL COMMENT 'Workspace id, NULL for HomeChat',
  `task_id` INT NULL COMMENT 'Task id this conversation belongs to',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_conv_uid` (`conv_uid`),
  KEY `ix_chat_history_workspace_id` (`workspace_id`),
  KEY `ix_chat_history_sys_code` (`sys_code`),
  KEY `ix_chat_history_task_id` (`task_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: chat_history_message
CREATE TABLE IF NOT EXISTS `chat_history_message` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT 'autoincrement id',
  `conv_uid` VARCHAR(255) NOT NULL COMMENT 'Conversation record unique id',
  `index` INT NOT NULL COMMENT 'Message index',
  `round_index` INT NOT NULL COMMENT 'Message round index',
  `message_detail` LONGTEXT NULL COMMENT 'Message details, json format',
  `gmt_create` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Record creation time',
  `gmt_modified` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Record update time',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_conversation_message` (`conv_uid`, `index`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: server_app_artifact
CREATE TABLE IF NOT EXISTS `server_app_artifact` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `task_id` INT NOT NULL,
  `workspace_id` INT NOT NULL,
  `type` VARCHAR(32) NOT NULL,
  `title` VARCHAR(256) NOT NULL,
  `content_ref` VARCHAR(512) NULL,
  `content_text` TEXT NULL,
  `current_version` INT NOT NULL DEFAULT 1,
  `provenance_json` TEXT NULL,
  `is_shared` TINYINT(1) NOT NULL DEFAULT 0,
  `created_by_agent` VARCHAR(128) NULL,
  `created_by_user` INT NULL,
  `gmt_create` DATETIME NULL DEFAULT CURRENT_TIMESTAMP,
  `gmt_modified` DATETIME NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `ix_server_app_artifact_task_id` (`task_id`),
  KEY `ix_server_app_artifact_workspace_id` (`workspace_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: server_app_artifact_version
CREATE TABLE IF NOT EXISTS `server_app_artifact_version` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `artifact_id` INT NOT NULL,
  `version` INT NOT NULL,
  `content_ref` VARCHAR(512) NULL,
  `diff_summary` TEXT NULL,
  `created_by` VARCHAR(128) NULL,
  `gmt_create` DATETIME NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `ix_server_app_artifact_version_artifact_id` (`artifact_id`),
  UNIQUE KEY `uk_artifact_version` (`artifact_id`, `version`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: derisk_serve_cron_job
CREATE TABLE IF NOT EXISTS `derisk_serve_cron_job` (
  `id` VARCHAR(64) NOT NULL AUTO_INCREMENT COMMENT 'Job unique identifier',
  `name` VARCHAR(255) NOT NULL COMMENT 'Job name',
  `description` TEXT NULL COMMENT 'Job description',
  `enabled` INT NULL DEFAULT 1 COMMENT 'Whether job is enabled (1=yes, 0=no)',
  `delete_after_run` INT NULL DEFAULT 0 COMMENT 'Delete after run (1=yes, 0=no)',
  `schedule_kind` VARCHAR(32) NOT NULL COMMENT 'Schedule kind (at/every/cron)',
  `schedule_at` VARCHAR(64) NULL COMMENT 'ISO datetime for ''at'' schedule',
  `schedule_every_ms` INT NULL COMMENT 'Interval in ms for ''every'' schedule',
  `schedule_anchor_ms` INT NULL COMMENT 'Anchor time for ''every'' schedule',
  `schedule_expr` VARCHAR(128) NULL COMMENT 'Cron expression for ''cron'' schedule',
  `schedule_tz` VARCHAR(64) NULL COMMENT 'Timezone',
  `payload_kind` VARCHAR(32) NOT NULL COMMENT 'Payload kind (agentTurn/toolCall/systemEvent)',
  `payload_data` JSON NULL COMMENT 'Payload data as JSON',
  `session_mode` VARCHAR(16) NULL DEFAULT isolated COMMENT 'Session mode (isolated/shared)',
  `conv_session_id` VARCHAR(64) NULL COMMENT 'Conversation session ID for shared sessions',
  `next_run_at_ms` INT NULL COMMENT 'Next run time in ms',
  `running_at_ms` INT NULL COMMENT 'Current run start time in ms',
  `last_run_at_ms` INT NULL COMMENT 'Last run time in ms',
  `last_status` VARCHAR(32) NULL COMMENT 'Last run status (ok/error/skipped)',
  `last_error` TEXT NULL COMMENT 'Last error message',
  `last_duration_ms` INT NULL COMMENT 'Last run duration in ms',
  `consecutive_errors` INT NULL DEFAULT 0 COMMENT 'Consecutive error count',
  `created_by_user_id` VARCHAR(128) NULL COMMENT 'Job creator user id',
  `gmt_create` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Record creation time',
  `gmt_modified` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Record update time',
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: derisk_serve_flow
CREATE TABLE IF NOT EXISTS `derisk_serve_flow` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT 'Auto increment id',
  `uid` VARCHAR(128) NOT NULL COMMENT 'Unique id',
  `dag_id` VARCHAR(128) NULL COMMENT 'DAG id',
  `label_info` VARCHAR(128) NULL COMMENT 'Flow label',
  `name` VARCHAR(128) NULL COMMENT 'Flow name',
  `flow_category` VARCHAR(64) NULL COMMENT 'Flow category',
  `flow_data` TEXT NULL COMMENT 'Flow data, JSON format',
  `description` VARCHAR(512) NULL COMMENT 'Flow description',
  `state` VARCHAR(32) NULL COMMENT 'Flow state',
  `error_message` VARCHAR(512) NULL COMMENT 'Error message',
  `source` VARCHAR(64) NULL COMMENT 'Flow source',
  `source_url` VARCHAR(512) NULL COMMENT 'Flow source url',
  `version` VARCHAR(32) NULL COMMENT 'Flow version',
  `define_type` VARCHAR(32) NULL DEFAULT json COMMENT 'Flow define type(json or python)',
  `editable` INT NULL COMMENT 'Editable, 0: editable, 1: not editable',
  `variables` TEXT NULL COMMENT 'Flow variables, JSON format',
  `user_name` VARCHAR(128) NULL COMMENT 'User name',
  `sys_code` VARCHAR(128) NULL COMMENT 'System code',
  `gmt_create` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Record creation time',
  `gmt_modified` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Record update time',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_uid` (`uid`),
  KEY `ix_derisk_serve_flow_dag_id` (`dag_id`),
  KEY `ix_derisk_serve_flow_sys_code` (`sys_code`),
  KEY `ix_derisk_serve_flow_name` (`name`),
  KEY `ix_derisk_serve_flow_uid` (`uid`),
  KEY `ix_derisk_serve_flow_user_name` (`user_name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: derisk_serve_variables
CREATE TABLE IF NOT EXISTS `derisk_serve_variables` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT 'Auto increment id',
  `key_info` VARCHAR(128) NOT NULL COMMENT 'Variable key',
  `name` VARCHAR(128) NULL COMMENT 'Variable name',
  `label_info` VARCHAR(128) NULL COMMENT 'Variable label',
  `value` TEXT NULL COMMENT 'Variable value, JSON format',
  `value_type` VARCHAR(32) NULL COMMENT 'Variable value type(string, int, float, bool)',
  `category` VARCHAR(32) NULL DEFAULT common COMMENT 'Variable category(common or secret)',
  `encryption_method` VARCHAR(32) NULL COMMENT 'Variable encryption method(fernet, simple, rsa, aes)',
  `salt` VARCHAR(128) NULL COMMENT 'Variable salt',
  `scope` VARCHAR(32) NULL DEFAULT global COMMENT 'Variable scope(global,flow,app,agent,datasource,flow_priv,agent_priv, etc)',
  `scope_key` VARCHAR(256) NULL COMMENT 'Variable scope key, default is empty, for scope is ''flow_priv'', the scope_key is dag id of flow',
  `enabled` INT NULL DEFAULT 1 COMMENT 'Variable enabled, 0: disabled, 1: enabled',
  `description` TEXT NULL COMMENT 'Variable description',
  `user_name` VARCHAR(128) NULL COMMENT 'User name',
  `sys_code` VARCHAR(128) NULL COMMENT 'System code',
  `gmt_create` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Record creation time',
  `gmt_modified` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Record update time',
  PRIMARY KEY (`id`),
  KEY `ix_derisk_serve_variables_name` (`name`),
  KEY `ix_derisk_serve_variables_user_name` (`user_name`),
  KEY `ix_derisk_serve_variables_key_info` (`key_info`),
  KEY `ix_derisk_serve_variables_sys_code` (`sys_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: connect_config
CREATE TABLE IF NOT EXISTS `connect_config` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT 'autoincrement id',
  `db_type` VARCHAR(255) NOT NULL COMMENT 'db type',
  `db_name` VARCHAR(255) NOT NULL COMMENT 'db name',
  `db_path` VARCHAR(255) NULL COMMENT 'file db path',
  `db_host` VARCHAR(255) NULL COMMENT 'db connect host(not file db)',
  `db_port` VARCHAR(255) NULL COMMENT 'db connect port(not file db)',
  `db_user` VARCHAR(255) NULL COMMENT 'db user',
  `db_pwd` VARCHAR(255) NULL COMMENT 'db password',
  `comment` TEXT NULL COMMENT 'db comment',
  `sys_code` VARCHAR(128) NULL COMMENT 'System code',
  `user_id` VARCHAR(128) NULL COMMENT 'User id',
  `user_name` VARCHAR(128) NULL COMMENT 'User name',
  `gmt_created` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Record creation time',
  `gmt_modified` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Record update time',
  `ext_config` TEXT NULL COMMENT 'Extended configuration, json format',
  `owner_workspace_id` INT NULL COMMENT 'Owner workspace id for workspace-owned datasets; NULL means global',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_db` (`db_name`),
  KEY `ix_connect_config_user_name` (`user_name`),
  KEY `idx_q_db_type` (`db_type`),
  KEY `idx_q_owner_workspace` (`owner_workspace_id`),
  KEY `ix_connect_config_sys_code` (`sys_code`),
  KEY `ix_connect_config_user_id` (`user_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: db_spec
CREATE TABLE IF NOT EXISTS `db_spec` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT 'autoincrement id',
  `datasource_id` INT NOT NULL COMMENT 'FK to connect_config.id',
  `db_name` VARCHAR(255) NOT NULL COMMENT 'Database name',
  `db_type` VARCHAR(64) NOT NULL COMMENT 'Database type',
  `spec_content` TEXT NOT NULL COMMENT 'JSON: table list index with summaries',
  `table_count` INT NULL COMMENT 'Total number of tables',
  `group_config` TEXT NULL COMMENT 'JSON: table grouping configuration',
  `relations` TEXT NULL COMMENT 'JSON: detected table relationships',
  `status` VARCHAR(32) NOT NULL DEFAULT generating COMMENT 'Status: ready, generating, failed',
  `gmt_created` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Record creation time',
  `gmt_modified` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Record update time',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_db_spec_datasource` (`datasource_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Table: table_spec
CREATE TABLE IF NOT EXISTS `table_spec` (
  `id` INT NOT NULL AUTO_INCREMENT COMMENT 'autoincrement id',
  `datasource_id` INT NOT NULL COMMENT 'FK to connect_config.id',
  `table_name` VARCHAR(255) NOT NULL COMMENT 'Table name',
  `table_comment` TEXT NULL COMMENT 'Table comment/description',
  `row_count` INT NULL COMMENT 'Approximate row count',
  `columns_json` TEXT NOT NULL COMMENT 'JSON: array of column definitions (name, type, nullable, default, comment, pk)',
  `indexes_json` TEXT NULL COMMENT 'JSON: array of index definitions (name, columns, unique)',
  `sample_data_json` TEXT NULL COMMENT 'JSON: sample rows from the table',
  `create_ddl` TEXT NULL COMMENT 'CREATE TABLE DDL statement',
  `foreign_keys_json` TEXT NULL COMMENT 'JSON: array of foreign key definitions (constrained_columns, referred_table, referred_columns)',
  `group_name` VARCHAR(128) NULL COMMENT 'Table group name for categorization',
  `gmt_created` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Record creation time',
  `gmt_modified` DATETIME NULL DEFAULT CURRENT_TIMESTAMP COMMENT 'Record update time',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_table_spec_ds_table` (`datasource_id`, `table_name`),
  KEY `idx_table_spec_ds` (`datasource_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

SET FOREIGN_KEY_CHECKS = 1;

-- ============================================================
-- End of DDL Script
-- ============================================================