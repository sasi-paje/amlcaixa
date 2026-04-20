import os
import sys
import glob
import pandas as pd
import pymysql
from pathlib import Path
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ─── CONFIG ───────────────────────────────────────────────────────────────────
DB_HOST   = os.getenv("DB_HOST", "localhost")
DB_PORT   = int(os.getenv("DB_PORT", "3306"))
DB_USER   = os.getenv("DB_USER", "")
DB_PASS   = os.getenv("DB_PASS", "")
DB_SCHEMA = os.getenv("DB_SCHEMA", "suhab_copy")
DB_TABLE = "COMPARACAO"
REQUIRED_COLS = ["CONTRATO", "CPF_MUTUÁRIO", "CPF_COOBRIGADO", "Nome_Arquivo"]
OUTPUT_CSV = "consolidado.csv"
OUTPUT_JOIN = "resultado_join.csv"
OUTPUT_FALTANTES = "resultado_faltantes_join.csv"

# ─── STEP 0: resolve Excel folder ─────────────────────────────────────────────
def get_excel_folder():
    cwd = Path.cwd()
    xlsx_in_cwd = list(cwd.glob("*.xlsx")) + list(cwd.glob("**/*.xlsx"))
    if xlsx_in_cwd:
        print(f"\n[INFO] Arquivos .xlsx encontrados em: {cwd}")
        return cwd
    folder = input("\nInforme o caminho da pasta com os arquivos Excel: ").strip()
    return Path(folder)

# Aliases: colunas que devem ser tratadas como equivalentes
COL_ALIASES = {
    "CPF_MUTUÁRIO": ["CPF_BENEFICIÁRIO", "CPF_MUTUARIO", "CPF_BENEFICIARIO"],
}

# ─── STEP 1: load Excel files and add Nome_Arquivo ────────────────────────────
def load_excels(folder: Path):
    xlsx_files = list(folder.glob("*.xlsx")) + list(folder.glob("**/*.xlsx"))
    # deduplicate
    xlsx_files = list({str(p): p for p in xlsx_files}.values())
    # skip temp lock files created by Excel (~$...)
    xlsx_files = [p for p in xlsx_files if not p.name.startswith("~$")]

    if not xlsx_files:
        print("[ERRO] Nenhum arquivo .xlsx encontrado.")
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"PASSO 1 — Carregando {len(xlsx_files)} arquivo(s) Excel")
    print(f"{'='*60}")

    dataframes = {}
    for path in xlsx_files:
        filename = path.name
        try:
            df = pd.read_excel(path, dtype=str)
            # Apply column aliases so downstream logic sees canonical names
            rename_map = {}
            for canonical, aliases in COL_ALIASES.items():
                if canonical not in df.columns:
                    for alias in aliases:
                        if alias in df.columns:
                            rename_map[alias] = canonical
                            print(f"  [ALIAS] '{alias}' → '{canonical}' em '{filename}'")
                            break
            if rename_map:
                df = df.rename(columns=rename_map)
            df["Nome_Arquivo"] = filename
            dataframes[filename] = df
            print(f"  [OK] {filename}  →  {len(df)} linhas, {len(df.columns)} colunas")
        except Exception as e:
            print(f"  [ERRO] {filename}: {e}")

    return dataframes

# ─── STEP 2: column audit ─────────────────────────────────────────────────────
def audit_columns(dataframes: dict):
    print(f"\n{'='*60}")
    print("PASSO 2 — Verificação de colunas")
    print(f"{'='*60}")

    col_map = {fname: set(df.columns) for fname, df in dataframes.items()}
    all_cols = set.union(*col_map.values()) if col_map else set()
    common_cols = set.intersection(*col_map.values()) if col_map else set()

    print(f"\nColunas presentes em TODOS os arquivos ({len(common_cols)}):")
    for c in sorted(common_cols):
        print(f"  • {c}")

    for fname, cols in col_map.items():
        exclusive = cols - common_cols
        if exclusive:
            print(f"\nColunas exclusivas de '{fname}':")
            for c in sorted(exclusive):
                print(f"  → {c}")

    print(f"\nVerificação das colunas obrigatórias:")
    for col in REQUIRED_COLS:
        present_in = [f for f, cols in col_map.items() if col in cols]
        missing_in = [f for f, cols in col_map.items() if col not in cols]
        status = "OK" if not missing_in else f"AUSENTE em {len(missing_in)} arquivo(s)"
        print(f"  {'✓' if not missing_in else '✗'} {col:25s} — {status}")
        if missing_in:
            for f in missing_in:
                print(f"       ↳ {f}")

# ─── STEP 3: consolidate CSV ──────────────────────────────────────────────────
def consolidate_csv(dataframes: dict, output_path: Path):
    print(f"\n{'='*60}")
    print("PASSO 3 — Consolidação em CSV")
    print(f"{'='*60}")

    frames = []
    # Normalize column lookup (strip whitespace)
    req = REQUIRED_COLS  # ["CONTRATO", "CPF_MUTUÁRIO", "CPF_COOBRIGADO", "Nome_Arquivo"]

    for fname, df in dataframes.items():
        # Build mapping: required col → actual col (case-insensitive fallback)
        col_upper = {c.upper().strip(): c for c in df.columns}
        row = {}
        for rc in req:
            if rc in df.columns:
                row[rc] = df[rc]
            elif rc.upper() in col_upper:
                row[rc] = df[col_upper[rc.upper()]]
            else:
                row[rc] = pd.Series([""] * len(df))
                print(f"  [AVISO] '{rc}' ausente em '{fname}' — preenchido com vazio")

        subset = pd.DataFrame(row)
        frames.append(subset)

    if not frames:
        print("[ERRO] Nenhum dado para consolidar.")
        sys.exit(1)

    consolidated = pd.concat(frames, ignore_index=True)
    consolidated.to_csv(output_path, index=False, encoding="utf-8-sig")
    print(f"\n  [OK] {output_path} gerado — {len(consolidated)} linhas totais")
    return consolidated

# ─── STEP 4: import CSV to MySQL ──────────────────────────────────────────────
def import_to_mysql(df: pd.DataFrame):
    print(f"\n{'='*60}")
    print("PASSO 4 — Importação para MySQL")
    print(f"{'='*60}")

    try:
        conn = pymysql.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASS,
            database=DB_SCHEMA,
            charset="utf8mb4",
            autocommit=False,
        )
    except Exception as e:
        print(f"  [ERRO DE CONEXÃO] Não foi possível conectar ao MySQL: {e}")
        print("  Verifique host, porta, schema e credenciais.")
        return None

    print(f"  [OK] Conectado a {DB_HOST}:{DB_PORT}/{DB_SCHEMA}")

    create_sql = f"""
    CREATE TABLE IF NOT EXISTS `{DB_TABLE}` (
        `CONTRATO`        VARCHAR(100),
        `CPF_MUTUÁRIO`    VARCHAR(20),
        `CPF_COOBRIGADO`  VARCHAR(20),
        `Nome_Arquivo`    VARCHAR(255)
    ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
    """

    with conn.cursor() as cur:
        cur.execute(create_sql)
        cur.execute(f"TRUNCATE TABLE `{DB_TABLE}`")

        insert_sql = f"""
        INSERT INTO `{DB_TABLE}` (`CONTRATO`, `CPF_MUTUÁRIO`, `CPF_COOBRIGADO`, `Nome_Arquivo`)
        VALUES (%s, %s, %s, %s)
        """
        rows = [
            (
                str(r["CONTRATO"]) if pd.notna(r["CONTRATO"]) else "",
                str(r["CPF_MUTUÁRIO"]) if pd.notna(r["CPF_MUTUÁRIO"]) else "",
                str(r["CPF_COOBRIGADO"]) if pd.notna(r["CPF_COOBRIGADO"]) else "",
                str(r["Nome_Arquivo"]) if pd.notna(r["Nome_Arquivo"]) else "",
            )
            for _, r in df.iterrows()
        ]
        cur.executemany(insert_sql, rows)
        conn.commit()
        print(f"  [OK] {cur.rowcount} linhas inseridas na tabela `{DB_TABLE}`")

    return conn

# ─── STEP 5: JOIN query ───────────────────────────────────────────────────────
def run_join_query(conn):
    print(f"\n{'='*60}")
    print("PASSO 5 — Executando JOIN")
    print(f"{'='*60}")

    query = f"""
    SELECT
        rp.alert_id,
        rp.cpf_titular_sem_mascara,
        REPLACE(REPLACE(rp.meta->>'$.data.cpf_conjuge', '.', ''), '-', '') AS cpf_conjuge,
        rp.nome_titular,
        rp.meta->>'$.data.nome_conjuge' AS nome_conjuge,
        c.CONTRATO,
        o.user_name
    FROM tb_resumo_prioridade AS rp
    LEFT JOIN log_hist_observacoes AS o
        ON rp.alert_id = o.alert_id
    INNER JOIN `{DB_TABLE}` AS c
        ON (
            rp.cpf_titular_sem_mascara = c.`CPF_MUTUÁRIO` COLLATE utf8mb4_0900_ai_ci
            OR rp.cpf_titular_sem_mascara = c.`CPF_COOBRIGADO` COLLATE utf8mb4_0900_ai_ci
            OR REPLACE(REPLACE(rp.meta->>'$.data.cpf_conjuge', '.', ''), '-', '') = c.`CPF_MUTUÁRIO` COLLATE utf8mb4_0900_ai_ci
            OR REPLACE(REPLACE(rp.meta->>'$.data.cpf_conjuge', '.', ''), '-', '') = c.`CPF_COOBRIGADO` COLLATE utf8mb4_0900_ai_ci
        )
    WHERE rp.statussuhab = 15
      AND o.new_json->>'$.statussuhab' = '15'
    """

    query_faltantes = f"""
    SELECT
        c.CONTRATO,
        c.`CPF_MUTUÁRIO`,
        c.`CPF_COOBRIGADO`,
        c.Nome_Arquivo
    FROM `{DB_TABLE}` AS c
    WHERE NOT EXISTS (
        SELECT 1
        FROM tb_resumo_prioridade AS rp
        LEFT JOIN log_hist_observacoes AS o ON rp.alert_id = o.alert_id
        WHERE (
            rp.cpf_titular_sem_mascara = c.`CPF_MUTUÁRIO` COLLATE utf8mb4_0900_ai_ci
            OR rp.cpf_titular_sem_mascara = c.`CPF_COOBRIGADO` COLLATE utf8mb4_0900_ai_ci
            OR REPLACE(REPLACE(rp.meta->>'$.data.cpf_conjuge', '.', ''), '-', '') = c.`CPF_MUTUÁRIO` COLLATE utf8mb4_0900_ai_ci
            OR REPLACE(REPLACE(rp.meta->>'$.data.cpf_conjuge', '.', ''), '-', '') = c.`CPF_COOBRIGADO` COLLATE utf8mb4_0900_ai_ci
        )
        AND rp.statussuhab = 15
        AND o.new_json->>'$.statussuhab' = '15'
    )
    """

    try:
        result_df = pd.read_sql(query, conn)
        if result_df.empty:
            print("  [INFO] resultado_join: 0 linhas.")
        else:
            output = Path(OUTPUT_JOIN)
            result_df.to_csv(output, index=False, encoding="utf-8-sig")
            print(f"  [OK] resultado_join: {len(result_df)} linha(s) — salvo em {output}")
            print(result_df.to_string(index=False))

        faltantes_df = pd.read_sql(query_faltantes, conn)
        if faltantes_df.empty:
            print("  [INFO] resultado_faltantes_join: 0 linhas.")
        else:
            output_f = Path(OUTPUT_FALTANTES)
            faltantes_df.to_csv(output_f, index=False, encoding="utf-8-sig")
            print(f"\n  [OK] resultado_faltantes_join: {len(faltantes_df)} linha(s) — salvo em {output_f}")
            print(faltantes_df.to_string(index=False))
    except Exception as e:
        print(f"  [ERRO] Falha ao executar a query: {e}")
    finally:
        conn.close()

# ─── MAIN ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    folder = get_excel_folder()
    dataframes = load_excels(folder)
    audit_columns(dataframes)
    consolidated = consolidate_csv(dataframes, folder / OUTPUT_CSV)
    conn = import_to_mysql(consolidated)
    if conn:
        run_join_query(conn)

    print(f"\n{'='*60}")
    print("Pipeline concluído.")
    print(f"{'='*60}\n")
