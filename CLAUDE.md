# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the pipeline

```bash
python3 pipeline.py
# Se os .xlsx estiverem no diretório atual, o script os detecta automaticamente.
# Caso contrário, informe o caminho quando solicitado.
```

## Dependencies

```bash
pip3 install pandas openpyxl pymysql python-dotenv --break-system-packages
```

## Environment

Credentials are in `.env` (not committed). Required variables:

```
DB_HOST=
DB_PORT=
DB_USER=
DB_PASS=
DB_SCHEMA=
```

## Architecture

`pipeline.py` is a single-file ETL with 5 sequential steps:

1. **load_excels** — reads all `.xlsx` from the folder, applies `COL_ALIASES` to normalize inconsistent column names across files (`CPF_BENEFICIÁRIO` → `CPF_MUTUÁRIO`, `NOME_BENEFICIÁRIO` / `MUTUARIO_PRINCIPAL` → `NOME_MUTUÁRIO`). Skips `~$` temp files.

2. **audit_columns** — prints which required columns are present/missing per file.

3. **consolidate_csv** — builds `consolidado.csv` with columns `CONTRATO`, `NOME_MUTUÁRIO`, `CPF`. CPF is a **UNION** of `CPF_MUTUÁRIO` and `CPF_COOBRIGADO` rows (each gets its own row). CPF is zero-padded to 11 digits. Deduplicates independently on `CONTRATO` and then on `CPF`.

4. **import_to_mysql** — DROPs and recreates `COMPARACAO` table in MySQL, then bulk-inserts the consolidado.

5. **run_join_query** — runs 3 queries against `suhab_copy` and saves results:
   - `resultado_join.csv` — CPFs matched in `tb_resumo_prioridade` with `statussuhab = 15`
   - `resultado_faltantes_join.csv` — CPFs from consolidado with no match
   - `resultado_join_statussuhab_diff15.csv` — CPFs matched but `statussuhab <> 15`

## Key design decisions

- The JOIN uses a single `CPF` column in `COMPARACAO` (after the UNION expansion), matching against both `cpf_titular_sem_mascara` and the JSON-extracted `meta->>'$.data.cpf_conjuge'` (with mask chars stripped via `REPLACE`).
- Collation mismatch between `tb_resumo_prioridade` (`utf8mb4_0900_ai_ci`) and `COMPARACAO` (`utf8mb4_unicode_ci`) is resolved with `COLLATE utf8mb4_0900_ai_ci` on the `COMPARACAO` side of the JOIN.
- The `diff15` query uses `UNION` instead of `OR` in the JOIN to avoid full table scans on the large `tb_resumo_prioridade` table.
- `read_timeout=300` / `write_timeout=300` are set on the connection to handle heavy queries.
