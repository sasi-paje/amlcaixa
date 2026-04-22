import os
import sys
import glob
import pandas as pd
import pymysql
from pathlib import Path
try:
    from dotenv import load_dotenv
    _env_path = Path(__file__).resolve().parent / ".env"
    load_dotenv(_env_path)
except ImportError:
    pass

# ─── CONFIG ───────────────────────────────────────────────────────────────────
DB_HOST   = os.getenv("DB_HOST", "localhost")
DB_PORT   = int(os.getenv("DB_PORT", "3306"))
DB_USER   = os.getenv("DB_USER", "")
DB_PASS   = os.getenv("DB_PASS", "")
DB_SCHEMA = os.getenv("DB_SCHEMA", "suhab_copy")
DB_TABLE  = "COMPARACAO"
REQUIRED_COLS = ["CONTRATO", "NOME_MUTUÁRIO", "CPF_MUTUÁRIO", "CPF_COOBRIGADO"]
OUTPUT_CSV      = "consolidado.csv"
OUTPUT_JOIN     = "resultado_join.csv"
OUTPUT_FALTANTES = "resultado_faltantes_join.csv"
OUTPUT_DIFF15   = "resultado_join_statussuhab_diff15.csv"

# ─── STEP 0: resolve Excel folder ─────────────────────────────────────────────
def get_excel_folder():
    cwd = Path.cwd()
    xlsx_in_cwd = list(cwd.glob("*.xlsx")) + list(cwd.glob("**/*.xlsx"))
    if xlsx_in_cwd:
        print(f"\n[INFO] Arquivos .xlsx encontrados em: {cwd}")
        return cwd
    folder = input("\nInforme o caminho da pasta com os arquivos Excel: ").strip()
    return Path(folder)

# Aliases: colunas equivalentes mapeadas para nome canônico
COL_ALIASES = {
    "CPF_MUTUÁRIO":  ["CPF_BENEFICIÁRIO",  "CPF_MUTUARIO",  "CPF_BENEFICIARIO"],
    "NOME_MUTUÁRIO": ["NOME_BENEFICIÁRIO", "MUTUARIO_PRINCIPAL", "NOME_BENEFICIARIO"],
}

# ─── STEP 1: load Excel files ─────────────────────────────────────────────────
def load_excels(folder: Path):
    xlsx_files = list(folder.glob("*.xlsx")) + list(folder.glob("**/*.xlsx"))
    xlsx_files = list({str(p): p for p in xlsx_files}.values())
    EXCLUDE = {"RESUMO.xlsx"}
    xlsx_files = [p for p in xlsx_files if not p.name.startswith("~$") and p.name not in EXCLUDE]

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
        missing_in = [f for f, cols in col_map.items() if col not in cols]
        status = "OK" if not missing_in else f"AUSENTE em {len(missing_in)} arquivo(s)"
        print(f"  {'✓' if not missing_in else '✗'} {col:25s} — {status}")
        for f in missing_in:
            print(f"       ↳ {f}")

# ─── STEP 3: consolidate CSV (UNION CPF_MUTUÁRIO + CPF_COOBRIGADO) ────────────
def consolidate_csv(dataframes: dict, output_path: Path):
    print(f"\n{'='*60}")
    print("PASSO 3 — Consolidação em CSV")
    print(f"{'='*60}")

    frames = []
    col_upper_map = lambda df: {c.upper().strip(): c for c in df.columns}

    def get_col(df, col):
        if col in df.columns:
            return df[col]
        up = col_upper_map(df)
        if col.upper() in up:
            return df[up[col.upper()]]
        return pd.Series([""] * len(df), index=df.index)

    for fname, df in dataframes.items():
        contrato     = get_col(df, "CONTRATO")
        nome_mut     = get_col(df, "NOME_MUTUÁRIO")
        cpf_mut      = get_col(df, "CPF_MUTUÁRIO")
        cpf_coob     = get_col(df, "CPF_COOBRIGADO")

        for col in REQUIRED_COLS:
            if col not in df.columns and col.upper() not in col_upper_map(df):
                print(f"  [AVISO] '{col}' ausente em '{fname}' — preenchido com vazio")

        # Parte 1: linhas do CPF_MUTUÁRIO
        df_mut = pd.DataFrame({
            "CONTRATO":      contrato.values,
            "NOME_MUTUÁRIO": nome_mut.values,
            "CPF":           cpf_mut.values,
        })

        # Parte 2: linhas do CPF_COOBRIGADO (somente onde não vazio)
        df_coob = pd.DataFrame({
            "CONTRATO":      contrato.values,
            "NOME_MUTUÁRIO": nome_mut.values,
            "CPF":           cpf_coob.values,
        })
        df_coob = df_coob[df_coob["CPF"].notna() & (df_coob["CPF"].str.strip() != "")]

        frames.extend([df_mut, df_coob])

    if not frames:
        print("[ERRO] Nenhum dado para consolidar.")
        sys.exit(1)

    consolidated = pd.concat(frames, ignore_index=True)
    consolidated["CPF"] = (
        consolidated["CPF"]
        .fillna("")
        .astype(str)
        .str.strip()
        .str.replace(r"\D", "", regex=True)
        .str.zfill(11)
    )
    before = len(consolidated)
    consolidated = consolidated.drop_duplicates(subset=["CONTRATO"])
    consolidated = consolidated.drop_duplicates(subset=["CPF"])
    removed = before - len(consolidated)
    if removed:
        print(f"  [INFO] {removed} linha(s) duplicada(s) removida(s)")

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
            connect_timeout=30,
            read_timeout=300,
            write_timeout=300,
        )
    except Exception as e:
        print(f"  [ERRO DE CONEXÃO] Não foi possível conectar ao MySQL: {e}")
        print("  Verifique host, porta, schema e credenciais.")
        return None

    print(f"  [OK] Conectado a {DB_HOST}:{DB_PORT}/{DB_SCHEMA}")

    with conn.cursor() as cur:
        cur.execute(f"DROP TABLE IF EXISTS `{DB_TABLE}`")
        cur.execute(f"""
            CREATE TABLE `{DB_TABLE}` (
                `CONTRATO`        VARCHAR(100),
                `NOME_MUTUÁRIO`   VARCHAR(255),
                `CPF`             VARCHAR(20)
            ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
        """)

        insert_sql = f"""
        INSERT INTO `{DB_TABLE}` (`CONTRATO`, `NOME_MUTUÁRIO`, `CPF`)
        VALUES (%s, %s, %s)
        """
        rows = [
            (
                str(r["CONTRATO"])      if pd.notna(r["CONTRATO"])      else "",
                str(r["NOME_MUTUÁRIO"]) if pd.notna(r["NOME_MUTUÁRIO"]) else "",
                str(r["CPF"])           if pd.notna(r["CPF"])           else "",
            )
            for _, r in df.iterrows()
        ]
        cur.executemany(insert_sql, rows)
        conn.commit()
        print(f"  [OK] {cur.rowcount} linhas inseridas na tabela `{DB_TABLE}`")

    return conn

# ─── STEP 5: JOIN queries ─────────────────────────────────────────────────────
def run_join_query(conn):
    print(f"\n{'='*60}")
    print("PASSO 5 — Executando JOIN")
    print(f"{'='*60}")

    # Bloco SELECT reutilizado nos 3 queries
    SELECT_BLOCK = f"""
        rp.alert_id,
        rp.cpf_titular_sem_mascara,
        REPLACE(REPLACE(rp.meta->>'$.data.cpf_conjuge', '.', ''), '-', '') AS cpf_conjuge,
        rp.nome_titular,
        rp.meta->>'$.data.nome_conjuge' AS nome_conjuge,
        c.CONTRATO,
        c.`NOME_MUTUÁRIO`,
        o.user_name
    """

    JOIN_COND = f"""
        rp.cpf_titular_sem_mascara = c.`CPF` COLLATE utf8mb4_0900_ai_ci
        OR REPLACE(REPLACE(rp.meta->>'$.data.cpf_conjuge', '.', ''), '-', '') = c.`CPF` COLLATE utf8mb4_0900_ai_ci
    """

    query_join = f"""
    SELECT {SELECT_BLOCK}
    FROM tb_resumo_prioridade AS rp
    LEFT JOIN log_hist_observacoes AS o ON rp.alert_id = o.alert_id
    INNER JOIN `{DB_TABLE}` AS c ON ({JOIN_COND})
    WHERE rp.statussuhab = 15
      AND o.new_json->>'$.statussuhab' = '15'
    """

    query_faltantes = f"""
    SELECT c.CONTRATO, c.`NOME_MUTUÁRIO`, c.`CPF`
    FROM `{DB_TABLE}` AS c
    WHERE NOT EXISTS (
        SELECT 1 FROM tb_resumo_prioridade AS rp
        WHERE rp.cpf_titular_sem_mascara = c.`CPF` COLLATE utf8mb4_0900_ai_ci
    )
    AND NOT EXISTS (
        SELECT 1 FROM tb_resumo_prioridade AS rp
        WHERE REPLACE(REPLACE(rp.meta->>'$.data.cpf_conjuge', '.', ''), '-', '') = c.`CPF` COLLATE utf8mb4_0900_ai_ci
    )
    """

    query_diff15 = f"""
    SELECT DISTINCT rp.alert_id, rp.statussuhab, {SELECT_BLOCK}
    FROM tb_resumo_prioridade AS rp
    LEFT JOIN log_hist_observacoes AS o ON rp.alert_id = o.alert_id
    INNER JOIN `{DB_TABLE}` AS c
        ON rp.cpf_titular_sem_mascara = c.`CPF` COLLATE utf8mb4_0900_ai_ci
    WHERE rp.statussuhab <> 15
    UNION
    SELECT DISTINCT rp.alert_id, rp.statussuhab, {SELECT_BLOCK}
    FROM tb_resumo_prioridade AS rp
    LEFT JOIN log_hist_observacoes AS o ON rp.alert_id = o.alert_id
    INNER JOIN `{DB_TABLE}` AS c
        ON REPLACE(REPLACE(rp.meta->>'$.data.cpf_conjuge', '.', ''), '-', '') = c.`CPF` COLLATE utf8mb4_0900_ai_ci
    WHERE rp.statussuhab <> 15
    """

    tasks = [
        (query_join,      Path(OUTPUT_JOIN),       "resultado_join",      None, "cpf_titular_sem_mascara"),
        (query_faltantes, Path(OUTPUT_FALTANTES),  "resultado_faltantes_join", None, None),
        (query_diff15,    Path(OUTPUT_DIFF15),      "resultado_join_statussuhab_diff15", ["user_name"], None),
    ]

    try:
        for query, output, label, drop_cols, dedup_col in tasks:
            result_df = pd.read_sql(query, conn)
            if drop_cols:
                result_df = result_df.drop(columns=[c for c in drop_cols if c in result_df.columns])
                result_df = result_df.drop_duplicates()
            if dedup_col and dedup_col in result_df.columns:
                result_df = result_df.drop_duplicates(subset=[dedup_col])
            if result_df.empty:
                print(f"  [INFO] {label}: 0 linhas.")
            else:
                result_df.to_csv(output, index=False, encoding="utf-8-sig")
                print(f"  [OK] {label}: {len(result_df)} linha(s) — salvo em {output}")
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
