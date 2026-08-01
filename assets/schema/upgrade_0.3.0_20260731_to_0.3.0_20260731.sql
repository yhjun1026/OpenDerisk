-- ============================================================
-- Incremental DDL Script for Derisk
-- Upgrade from version 0.3.0 to 0.3.0
-- Source DDL generated: 2026-07-31 22:38:51
-- Generated: 2026-07-31 22:39:41
-- ============================================================

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- ============================================================
-- Modified Tables
-- ============================================================

-- Table: connect_config
ALTER TABLE `connect_config` ADD INDEX `idx_q_owner_workspace` (`owner_workspace_id`);


SET FOREIGN_KEY_CHECKS = 1;

-- ============================================================
-- End of Incremental DDL Script
-- ============================================================