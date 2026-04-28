import os
import sys
import pandas as pd
import pymysql
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:
    pass

# ─── CONFIG ───────────────────────────────────────────────────────────────────
DB_HOST   = os.getenv("DB_HOST", "localhost")
DB_PORT   = int(os.getenv("DB_PORT", "3306"))
DB_USER   = os.getenv("DB_USER", "")
DB_PASS   = os.getenv("DB_PASS", "")
DB_SCHEMA = os.getenv("DB_SCHEMA", "suhab_copy")
DB_TABLE  = "COMPARACAO_CAIXA"

OUTPUT_CSV       = "consolidado_caixa.csv"
OUTPUT_MATCH     = "consolidado_suhab_caixa_match.csv"
OUTPUT_NOT_CAIXA = "consolidado_suhab_caixa_not_match_lado_caixa.csv"
OUTPUT_NOT_SUHAB = "consolidado_suhab_caixa_not_match_lado_suhab.csv"

CPF_SOURCE_COLS = [
    "CPF_BENEFICIÁRIO",
    "CPF_MUTUÁRIO",
    "CPF_COOBRIGADO",
    "CPF_COOBRIGADO_2",
]

# ─── STEP 1: carrega e consolida os xlsx ──────────────────────────────────────
def load_and_union(folder: Path) -> pd.DataFrame:
    xlsx_files = [
        p for p in folder.glob("*.xlsx")
        if not p.name.startswith("~$") and p.name != "RESUMO.xlsx"
    ]
    if not xlsx_files:
        print("[ERRO] Nenhum arquivo .xlsx encontrado.")
        sys.exit(1)

    print(f"[INFO] {len(xlsx_files)} arquivo(s) encontrado(s).\n")

    frames = []
    for path in xlsx_files:
        df = pd.read_excel(path, dtype=str)
        print(f"  {path.name}")

        contrato_col = next((c for c in df.columns if c.upper().strip() == "CONTRATO"), None)
        if not contrato_col:
            print(f"    [AVISO] coluna CONTRATO ausente — ignorando arquivo.")
            continue

        for cpf_col in CPF_SOURCE_COLS:
            if cpf_col not in df.columns:
                continue
            chunk = pd.DataFrame({
                "CONTRATO": df[contrato_col].values,
                "CPF":      df[cpf_col].values,
            })
            chunk = chunk[chunk["CPF"].notna() & (chunk["CPF"].astype(str).str.strip() != "")]
            if not chunk.empty:
                print(f"    + {cpf_col}: {len(chunk)} linhas")
            frames.append(chunk)

    if not frames:
        print("[ERRO] Nenhum dado coletado.")
        sys.exit(1)

    result = pd.concat(frames, ignore_index=True)

    result["CPF"] = (
        result["CPF"]
        .astype(str)
        .str.strip()
        .str.replace(r"\D", "", regex=True)
        .str.zfill(11)
    )

    # Remove CPFs inválidos: vazios ou somente zeros (ex: 00000000000)
    result = result[result["CPF"].str.strip("0") != ""]

    before = len(result)
    result = result.drop_duplicates(subset=["CONTRATO", "CPF"])
    removed = before - len(result)

    print(f"\n[INFO] Total antes da deduplicação: {before}")
    print(f"[INFO] Duplicatas removidas (CONTRATO+CPF): {removed}")
    print(f"[INFO] Total final: {len(result)}")

    return result

# ─── STEP 2: importa para MySQL ───────────────────────────────────────────────
def import_to_mysql(df: pd.DataFrame):
    print(f"\n{'='*60}")
    print("PASSO 2 — Importação para MySQL")
    print(f"{'='*60}")

    try:
        conn = pymysql.connect(
            host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASS,
            database=DB_SCHEMA, charset="utf8mb4", autocommit=False,
            connect_timeout=30, read_timeout=300, write_timeout=300,
        )
    except Exception as e:
        print(f"  [ERRO DE CONEXÃO] {e}")
        return None

    print(f"  [OK] Conectado a {DB_HOST}:{DB_PORT}/{DB_SCHEMA}")

    with conn.cursor() as cur:
        cur.execute(f"DROP TABLE IF EXISTS `{DB_TABLE}`")
        cur.execute(f"""
            CREATE TABLE `{DB_TABLE}` (
                `CONTRATO` VARCHAR(100),
                `CPF`      VARCHAR(20)
            ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
        """)
        rows = [(str(r["CONTRATO"]), str(r["CPF"])) for _, r in df.iterrows()]
        cur.executemany(f"INSERT INTO `{DB_TABLE}` (`CONTRATO`, `CPF`) VALUES (%s, %s)", rows)
        conn.commit()
        print(f"  [OK] {cur.rowcount} linhas inseridas em `{DB_TABLE}`")

    return conn

# ─── STEP 3: gera os três CSVs de match/not-match ────────────────────────────
def run_match_queries(conn, folder: Path):
    print(f"\n{'='*60}")
    print("PASSO 3 — Gerando match / not-match")
    print(f"{'='*60}")

    SELECT_RP = """
        rp.alert_id,
        UPPER(rp.nome_titular)        AS nome_titular,
        rp.cpf_titular_sem_mascara,
        REPLACE(REPLACE(rp.meta->>'$.data.cpf_conjuge', '.', ''), '-', '') AS cpf_conjuge,
        rp.data_de_nascimento_titular,
        rp.statussuhab,
        sm.status_name,
        c.CONTRATO,
        c.CPF                         AS cpf_caixa
    """

    # match: UNION para evitar full table scan com OR
    query_match = f"""
    SELECT DISTINCT {SELECT_RP}
    FROM tb_resumo_prioridade AS rp
    LEFT JOIN status_menu AS sm ON rp.statussuhab = sm.ids_status
    INNER JOIN `{DB_TABLE}` AS c
        ON rp.cpf_titular_sem_mascara = c.`CPF` COLLATE utf8mb4_0900_ai_ci
    UNION
    SELECT DISTINCT {SELECT_RP}
    FROM tb_resumo_prioridade AS rp
    LEFT JOIN status_menu AS sm ON rp.statussuhab = sm.ids_status
    INNER JOIN `{DB_TABLE}` AS c
        ON REPLACE(REPLACE(rp.meta->>'$.data.cpf_conjuge', '.', ''), '-', '') = c.`CPF` COLLATE utf8mb4_0900_ai_ci
    """

    # not-match lado caixa: CPFs da caixa sem correspondência no suhab
    query_not_caixa = f"""
    SELECT c.CONTRATO, c.CPF
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

    # not-match lado suhab: registros do suhab sem correspondência na caixa
    SELECT_RP_ONLY = """
        rp.alert_id,
        UPPER(rp.nome_titular)        AS nome_titular,
        rp.cpf_titular_sem_mascara,
        REPLACE(REPLACE(rp.meta->>'$.data.cpf_conjuge', '.', ''), '-', '') AS cpf_conjuge,
        rp.data_de_nascimento_titular,
        rp.statussuhab,
        sm.status_name
    """
    query_not_suhab = f"""
    SELECT DISTINCT {SELECT_RP_ONLY}
    FROM tb_resumo_prioridade AS rp
    LEFT JOIN status_menu AS sm ON rp.statussuhab = sm.ids_status
    WHERE rp.statussuhab = 15
    AND NOT EXISTS (
        SELECT 1 FROM `{DB_TABLE}` AS c
        WHERE rp.cpf_titular_sem_mascara = c.`CPF` COLLATE utf8mb4_0900_ai_ci
    )
    AND NOT EXISTS (
        SELECT 1 FROM `{DB_TABLE}` AS c
        WHERE REPLACE(REPLACE(rp.meta->>'$.data.cpf_conjuge', '.', ''), '-', '') = c.`CPF` COLLATE utf8mb4_0900_ai_ci
    )
    """

    tasks = [
        (query_match,      folder / OUTPUT_MATCH,     "match"),
        (query_not_caixa,  folder / OUTPUT_NOT_CAIXA, "not_match_lado_caixa"),
        (query_not_suhab,  folder / OUTPUT_NOT_SUHAB, "not_match_lado_suhab"),
    ]

    try:
        for query, output, label in tasks:
            print(f"\n  Executando {label}...", end=" ", flush=True)
            result = pd.read_sql(query, conn)
            result.to_csv(output, index=False, encoding="utf-8-sig")
            print(f"{len(result)} linha(s) → {output.name}")
    except Exception as e:
        print(f"\n  [ERRO] {e}")
    finally:
        conn.close()

# ─── STEP 4: split match por statussuhab ─────────────────────────────────────
def split_match_by_status(folder: Path):
    print(f"\n{'='*60}")
    print("PASSO 4 — Arquivos derivados por statussuhab")
    print(f"{'='*60}")

    match_path = folder / OUTPUT_MATCH
    if not match_path.exists():
        print(f"  [AVISO] {OUTPUT_MATCH} não encontrado — pulando.")
        return

    match = pd.read_csv(match_path, dtype=str)
    for status, group in match.groupby("statussuhab"):
        filename = f"match_status_{status}.csv"
        group.to_csv(folder / filename, index=False, encoding="utf-8-sig")
        print(f"  [OK] {filename}: {len(group)} linha(s)")

# ─── MAIN ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    folder = Path.cwd()

    print(f"\n{'='*60}")
    print("PASSO 1 — Consolidação das planilhas")
    print(f"{'='*60}")
    df = load_and_union(folder)
    output_csv = folder / OUTPUT_CSV
    df.to_csv(output_csv, index=False, encoding="utf-8-sig")
    print(f"\n[OK] {output_csv.name} gerado com {len(df)} linhas.")

    conn = import_to_mysql(df)
    if conn:
        run_match_queries(conn, folder)

    split_match_by_status(folder)

    print(f"\n{'='*60}")
    print("Pipeline concluído.")
    print(f"{'='*60}\n")
