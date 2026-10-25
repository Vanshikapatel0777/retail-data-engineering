# Retail Data Engineering — Troubleshooting Guide

## PostgreSQL Issues

### Problem: "password authentication failed for user postgres"

**Diagnosis steps (run in PowerShell — no password revealed):**

```powershell
# 1. Check if PostgreSQL service is running
Get-Service -Name "postgresql*"

# 2. Check if port 5432 is listening
netstat -an | Select-String ":5432"

# 3. Test connection without password (as local admin, if pg_hba allows trust locally)
psql -U postgres -h localhost -p 5432 -c "SELECT version();"
```

**Safe password reset procedure (Windows):**

> ⚠️ This temporarily allows passwordless local login. Revert immediately after.

```powershell
# 1. Find pg_hba.conf
# Usually at: C:\Program Files\PostgreSQL\17\data\pg_hba.conf

# 2. Open pg_hba.conf in Notepad (as Administrator)
# Find the line:
#   host    all    all    127.0.0.1/32    scram-sha-256
# Temporarily change to:
#   host    all    all    127.0.0.1/32    trust

# 3. Restart PostgreSQL service
Restart-Service postgresql-x64-17

# 4. Set new password
psql -U postgres -h localhost -c "ALTER USER postgres PASSWORD 'your_new_password';"

# 5. Immediately revert pg_hba.conf back to scram-sha-256
# Then restart service again:
Restart-Service postgresql-x64-17
```

**Update .env after reset:**
```
DB_PASSWORD=your_new_password
```

---

### Problem: "PostgreSQL service is not running"

```powershell
# Start the service
Start-Service postgresql-x64-17

# Or (find exact service name first):
Get-Service -Name "postgresql*"
Start-Service "postgresql-x64-17"  # adjust to match exact name
```

---

### Problem: "database retail_dw does not exist"

```powershell
# Create the database
psql -U postgres -h localhost -c "CREATE DATABASE retail_dw;"

# Or via the pipeline:
.venv\Scripts\Activate.ps1
python -m src.run_pipeline --create-db
```

---

### Problem: Port 5432 not listening / connection refused

```powershell
# Check for port conflicts
netstat -an | Select-String ":5432"

# Check if another PostgreSQL instance is on a different port
Get-Service -Name "postgresql*" | Select-Object Name, Status
```

---

## Python / Environment Issues

### Problem: "ModuleNotFoundError: No module named 'src'"

Run from the project root directory, not from inside `src/`:

```powershell
# Correct:
python -m src.run_pipeline

# Wrong (do NOT do this):
cd src
python run_pipeline.py
```

Or activate the venv first:

```powershell
.venv\Scripts\Activate.ps1
python -m src.run_pipeline
```

---

### Problem: "FileNotFoundError: data/raw/online_retail_II.xlsx"

Download the dataset from Kaggle:
1. Go to: https://www.kaggle.com/datasets/mashlyn/online-retail-ii-uci
2. Click Download
3. Extract the zip
4. Place `online_retail_II.xlsx` at `data\raw\online_retail_II.xlsx`

---

### Problem: uv sync fails

```powershell
# Clear uv cache and retry
uv cache clean
uv sync
```

---

## Data Issues

### Problem: Reconciliation mismatch (clean + rejected ≠ input)

Check the logs for details:
```powershell
cat logs\pipeline.log | Select-String "Reconciliation"
```

This usually means a bug was introduced in duplicate handling. The duplicate count must be included in the rejected count.

---

### Problem: All rows rejected

Check the rejected CSV for the rejection reasons:
```powershell
# View first few rejected rows
Import-Csv data\rejected\retail_rejected.csv | Select-Object -First 10 | Format-Table
```

Common causes:
- Column mapping failed (source has different header names)
- Entire price column is text/object type (openpyxl read error)

---

## Security

### Rotating a leaked credential

If your DB_PASSWORD was accidentally committed to Git:

1. **Immediately change the password in PostgreSQL:**
   ```sql
   ALTER USER postgres PASSWORD 'new_strong_password';
   ```

2. **Update .env:**
   ```
   DB_PASSWORD=new_strong_password
   ```

3. **Remove from Git history** (if committed):
   ```powershell
   git filter-branch --force --index-filter `
     "git rm --cached --ignore-unmatch .env" `
     --prune-empty --tag-name-filter cat -- --all
   git push origin --force --all
   ```
   
4. **Consider the old password compromised** — change any other systems using it.

5. **Add pre-commit hooks** to prevent future credential commits:
   ```powershell
   pip install pre-commit
   # Create .pre-commit-config.yaml with detect-secrets hook
   ```
