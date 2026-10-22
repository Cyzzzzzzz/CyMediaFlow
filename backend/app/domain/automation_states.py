"""Persisted automation state messages shared by reconciliation and file operations."""

LEGACY_RENAME_PENDING_REASON = "等待下载器确认重命名"
RENAME_PENDING_REASON = "等待下载器确认重命名，将自动复查，无需人工审核"
RENAME_CONFIRMATION_TIMEOUT_SECONDS = 120
RENAME_TIMEOUT_REASON = "下载器重命名确认超时，请核对文件后点击继续整理重试"
