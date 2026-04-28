# Relatório de Validação de Contemplados — Programa Amazonas Meu Lar

---

## Origem dos dados

O processo cruza duas fontes: os relatórios analíticos enviados pela CAIXA Econômica Federal (9 arquivos Excel) e o sistema interno SUHAB. O objetivo é identificar quais contemplados constam em ambas as bases, quais estão em apenas uma delas e qual é a situação cadastral de cada um.

---

## Base consolidada da CAIXA

O arquivo `consolidado_caixa.csv` reúne **2.979 registros únicos** (par CONTRATO + CPF) extraídos dos 9 relatórios Excel, considerando todas as colunas de CPF disponíveis — `CPF_MUTUÁRIO`, `CPF_BENEFICIÁRIO`, `CPF_COOBRIGADO` e `CPF_COOBRIGADO_2` — expandidas via UNION ALL. CPFs zerados ou em branco foram descartados. O arquivo possui **2.979 CPFs únicos** distribuídos em **2.649 contratos únicos**.

---

## Resultado do cruzamento com o SUHAB

O cruzamento compara cada CPF da base CAIXA contra o `cpf_titular_sem_mascara` e o `cpf_conjuge` da tabela `tb_resumo_prioridade`. Resultados:

- **2.953 CPFs da CAIXA** encontraram correspondência no SUHAB, gerando **3.127 combinações** (um CPF pode casar com mais de um alert_id) e **2.820 alert_ids únicos** — arquivo `consolidado_suhab_caixa_match.csv`.
- **26 CPFs da CAIXA** não foram localizados no SUHAB — arquivo `consolidado_suhab_caixa_not_match_lado_caixa.csv`.
- **189 pessoas** com `statussuhab = 15` no SUHAB não possuem CPF correspondente nos relatórios da CAIXA — arquivo `consolidado_suhab_caixa_not_match_lado_suhab.csv`.

---

## Distribuição de status nos registros com match

| Status | Descrição               | Registros |
|-------:|-------------------------|----------:|
| 15     | Contrato Assinado       |   2.885   |
|  0     | (sem status definido)   |     239   |
| 11     | —                       |       2   |
| 14     | —                       |       1   |
| **Total** |                      | **3.127** |

---

## Síntese executiva

```
┌───────────────────────────────────────────────────────────────┬────────────┐
│                           Situação                            │ Quantidade │
├───────────────────────────────────────────────────────────────┼────────────┤
│ Registros consolidados da CAIXA (CONTRATO + CPF únicos)       │   2.979    │
├───────────────────────────────────────────────────────────────┼────────────┤
│ CPFs da CAIXA com match no SUHAB                              │   2.953    │
├───────────────────────────────────────────────────────────────┼────────────┤
│   → Com status 15 (Contrato Assinado)                         │   2.885    │
├───────────────────────────────────────────────────────────────┼────────────┤
│   → Com status diferente de 15                                │     242    │
├───────────────────────────────────────────────────────────────┼────────────┤
│ CPFs da CAIXA sem nenhum match no SUHAB                       │      26    │
├───────────────────────────────────────────────────────────────┼────────────┤
│ No SUHAB (status 15) sem correspondência na CAIXA             │     189    │
└───────────────────────────────────────────────────────────────┴────────────┘
```

---

## Visão geral dos arquivos gerados

```
┌─────────────────────────────────────────────────────────┬───────────┬──────────────────────────────────────────────────────────────────────────────┐
│ Arquivo                                                 │ Registros │ Descrição                                                                    │
├─────────────────────────────────────────────────────────┼───────────┼──────────────────────────────────────────────────────────────────────────────┤
│ consolidado_caixa.csv                                   │   2.979   │ UNION de CPF_MUTUÁRIO, CPF_BENEFICIÁRIO, CPF_COOBRIGADO, CPF_COOBRIGADO_2    │
├─────────────────────────────────────────────────────────┼───────────┼──────────────────────────────────────────────────────────────────────────────┤
│ consolidado_suhab_caixa_match.csv                       │   3.127   │ CPFs da CAIXA com match no SUHAB (por cpf_titular ou cpf_conjuge).           │
│                                                         │           │ 2.820 alert_ids únicos — 307 linhas duplicadas pois o mesmo alert_id casou   │
│                                                         │           │ duas vezes quando titular E cônjuge ambos constam na base da CAIXA           │
├─────────────────────────────────────────────────────────┼───────────┼──────────────────────────────────────────────────────────────────────────────┤
│   match_status_15.csv                                   │   2.885   │ Derivado do match — statussuhab = 15 (Contrato Assinado)                     │
├─────────────────────────────────────────────────────────┼───────────┼──────────────────────────────────────────────────────────────────────────────┤
│   match_status_0.csv                                    │     239   │ Derivado do match — statussuhab = 0                                          │
├─────────────────────────────────────────────────────────┼───────────┼──────────────────────────────────────────────────────────────────────────────┤
│   match_status_11.csv                                   │       2   │ Derivado do match — statussuhab = 11                                         │
├─────────────────────────────────────────────────────────┼───────────┼──────────────────────────────────────────────────────────────────────────────┤
│   match_status_14.csv                                   │       1   │ Derivado do match — statussuhab = 14                                         │
├─────────────────────────────────────────────────────────┼───────────┼──────────────────────────────────────────────────────────────────────────────┤
│ consolidado_suhab_caixa_not_match_lado_caixa.csv        │      26   │ CPFs da CAIXA sem nenhuma correspondência no SUHAB                           │
├─────────────────────────────────────────────────────────┼───────────┼──────────────────────────────────────────────────────────────────────────────┤
│ consolidado_suhab_caixa_not_match_lado_suhab.csv        │     189   │ Status 15 no SUHAB cujo CPF não consta em nenhum Excel da CAIXA              │
└─────────────────────────────────────────────────────────┴───────────┴──────────────────────────────────────────────────────────────────────────────┘
```
