# Resumo — Cruzamento Programa Amazonas Meu Lar x CAIXA

## Consolidado

| Métrica | Quantidade |
|---|---|
| Total de registros únicos (CONTRATO + CPF) | **2.650** |
| Arquivos Excel processados | **9** |

## Resultados do cruzamento com SUHAB

| Arquivo | Registros | Situação |
|---|---|---|
| `resultado_join.csv` | **2.633** | Encontrados em `tb_resumo_prioridade` com `statussuhab = 15` |
| `resultado_faltantes_join.csv` | **6** | **Não encontrados** no sistema SUHAB |
| `resultado_join_statussuhab_diff15.csv` | **98** | Encontrados porém com `statussuhab ≠ 15` |

## Cobertura

| | Qtd | % |
|---|---|---|
| Localizados (status 15) | **2.633** | 99,4% |
| Localizados (status ≠ 15) | **98** | 3,7% |
| Não localizados | **6** | 0,2% |
