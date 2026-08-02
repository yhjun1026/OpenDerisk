-- Upgrade script: Add sso_auto_login_provider column for automatic SSO login

-- Add sso_auto_login_provider column if not exists
ALTER TABLE `oauth2_config`
  ADD COLUMN IF NOT EXISTS `sso_auto_login_provider` VARCHAR(64) NULL COMMENT 'Provider ID for automatic SSO login redirect' AFTER `default_role`;