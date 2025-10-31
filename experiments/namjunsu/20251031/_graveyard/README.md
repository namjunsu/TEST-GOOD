# Graveyard - Safe File Quarantine

This directory holds files that are candidates for deletion, isolated for a **7-day quarantine period** before final removal.

## Philosophy

- **Never delete immediately** - Always quarantine first
- **Preserve directory structure** - Files maintain their original paths
- **Track everything** - All operations logged in `scripts/cleanup_plan.csv`
- **Reversible** - Easy restoration if needed

## Workflow

### 1. Preview (Dry-Run)
```bash
make cleanup-dry
```
Shows what files would be isolated without making changes.

### 2. Isolate
```bash
make cleanup-isolate
```
Moves unused files to this graveyard directory and updates CSV tracker.

### 3. Quarantine Period
Files remain here for **7 days** from `quarantine_date`.

During this time:
- Backend continues to run normally
- If a file is needed, restore immediately
- Review CSV to confirm isolation is correct

### 4. Restore (if needed)
```bash
# Restore all quarantined files
make cleanup-restore

# Or restore specific file
python scripts/cleanup_restore.py path/to/file.py
```

### 5. Final Deletion
```bash
make cleanup-apply
```
Deletes files that have been quarantined for 7+ days.

**Note**: This requires confirmation unless `--force` is used.

## CSV Tracker

All quarantined files are tracked in `scripts/cleanup_plan.csv`:

| Field | Description |
|-------|-------------|
| `path` | Original file path |
| `reason` | Why it was isolated |
| `restore_method` | Command to restore |
| `quarantine_date` | Date isolated (YYYY-MM-DD) |
| `status` | pending, quarantined, deleted, restored |

## Check Status

```bash
make cleanup-status
```

Shows:
- Total quarantined files
- Status breakdown
- Days remaining until deletion

## Safety Features

1. **False Positive Protection**: Known-used files (like `app/alerts.py`, `app/rag/pipeline.py`) are excluded from isolation
2. **Atomic Operations**: Files moved (not copied+deleted)
3. **Audit Trail**: Full history in CSV
4. **Manual Override**: Can always restore or force-delete

## Example Timeline

| Day | Action | Status |
|-----|--------|--------|
| Day 0 | `make cleanup-isolate` | File moved to graveyard |
| Day 1-6 | Review, test system | Quarantine period |
| Day 3 | (Optional) `make cleanup-restore` | File restored if needed |
| Day 7+ | `make cleanup-apply` | Eligible for deletion |

## Tips

- Run `make cleanup-dry` first to preview
- Check `cleanup-status` daily during quarantine
- If unsure, restore and manually review
- After 7 days, system prompts for confirmation before delete

## Who Uses This?

- **Automated audits**: `scripts/audit_usage.py` identifies candidates
- **Manual cleanup**: Developers can isolate specific files
- **CI/CD**: Periodic cleanup during maintenance windows

## Recover Deleted Files?

Once `cleanup-apply` runs and files are deleted, recovery options:
1. Git history (if committed previously)
2. System backups (if configured)
3. Re-create from documentation

**Best practice**: Always review CSV before running `cleanup-apply`.
