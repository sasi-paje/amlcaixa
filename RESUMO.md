# Relatório de Validação de Contemplados — Programa Amazonas Meu Lar

---

## Origem dos dados

O processo de validação cruza duas fontes distintas: os relatórios analíticos enviados pela CAIXA Econômica Federal (arquivos Excel) e o sistema interno de gestão habitacional SUHAB. O objetivo é identificar quais contemplados constam em ambas as bases, quais estão em apenas uma delas e qual é a situação cadastral de cada um.

---

## Base consolidada da CAIXA

O arquivo `consolidado.csv` reúne os **2.650 mutuários** extraídos dos relatórios Excel da CAIXA, considerando exclusivamente o CPF do mutuário principal. Registros duplicados por CPF ou por número de contrato foram eliminados, garantindo unicidade.

---

## Resultado do cruzamento com o SUHAB

Do total de 2.650 mutuários consolidados, **2.625 (99,1%)** foram localizados no sistema SUHAB — resultado registrado no arquivo `match_geral.csv`. Desses:

- **2.591** possuem o contrato efetivamente assinado (status 15 — *Contrato Assinado*), registrados em `resultado_join.csv` e detalhados em `match_status_15.csv`;
- **35** foram localizados no SUHAB, porém com status diferente de 15, indicando que o processo contratual ainda não foi concluído ou houve alteração posterior. Esses casos constam em `resultado_join_statussuhab_diff15.csv` e são detalhados em `match_status_0.csv` (32 casos), `match_status_11.csv` (2 casos) e `match_status_14.csv` (1 caso);
- **25** constam nos relatórios da CAIXA mas **não foram localizados no SUHAB**, registrados em `resultado_faltantes_join.csv` e em `not_match-somente-lado-caixa.csv`. Esses casos requerem verificação, pois podem indicar divergência de CPF entre os dois sistemas ou ausência de cadastro no SUHAB.

---

## Contemplados no SUHAB sem correspondência nos relatórios da CAIXA

O arquivo `not_match-somente-lado-suhab.csv` lista **239 pessoas** que possuem contrato assinado confirmado no SUHAB (status 15) mas cujos CPFs **não constam em nenhum dos arquivos Excel** recebidos da CAIXA. Esses casos indicam que a CAIXA ainda não incluiu esses contemplados nas remessas de relatórios enviadas à SUHAB, ou que há divergência no número do CPF registrado em cada sistema.

---

## Síntese executiva

```
┌────────────────────────────────────────────┬────────────┐
│                  Situação                  │ Quantidade │
├────────────────────────────────────────────┼────────────┤
│ Mutuários consolidados (base CAIXA)        │   2.650    │
├────────────────────────────────────────────┼────────────┤
│ Localizados no SUHAB                       │   2.625    │
├────────────────────────────────────────────┼────────────┤
│ Com contrato assinado (status 15)          │   2.591    │
├────────────────────────────────────────────┼────────────┤
│ Localizados com status diferente de 15     │      35    │
├────────────────────────────────────────────┼────────────┤
│ Na CAIXA sem registro no SUHAB             │      25    │
├────────────────────────────────────────────┼────────────┤
│ No SUHAB (status 15) sem registro na CAIXA │     239    │
└────────────────────────────────────────────┴────────────┘
```

---

## Visão geral dos arquivos

```
┌───────────────────────────────────────┬───────────┬─────────────────────────────────────────────────────────────────┐
│                Arquivo                │ Registros │                            Descrição                            │
├───────────────────────────────────────┼───────────┼─────────────────────────────────────────────────────────────────┤
│ consolidado.csv                       │   2.650   │ Excel CAIXA — só CPF_MUTUÁRIO, sem duplicata de CPF ou CONTRATO │
├───────────────────────────────────────┼───────────┼─────────────────────────────────────────────────────────────────┤
│ resultado_join.csv                    │   2.591   │ Match SUHAB com status = 15                                     │
├───────────────────────────────────────┼───────────┼─────────────────────────────────────────────────────────────────┤
│ resultado_join_statussuhab_diff15.csv │      35   │ Match SUHAB com status ≠ 15                                     │
├───────────────────────────────────────┼───────────┼─────────────────────────────────────────────────────────────────┤
│ resultado_faltantes_join.csv          │      25   │ No Excel, sem match no SUHAB                                    │
├───────────────────────────────────────┼───────────┼─────────────────────────────────────────────────────────────────┤
│ match_geral.csv                       │   2.625   │ União dos dois joins (sem duplicata de CPF ou CONTRATO)         │
├───────────────────────────────────────┼───────────┼─────────────────────────────────────────────────────────────────┤
│ match_status_15.csv                   │   2.590   │ match_geral filtrado status = 15                                │
├───────────────────────────────────────┼───────────┼─────────────────────────────────────────────────────────────────┤
│ match_status_0.csv                    │      32   │ match_geral filtrado status = 0                                 │
├───────────────────────────────────────┼───────────┼─────────────────────────────────────────────────────────────────┤
│ match_status_11.csv                   │       2   │ match_geral filtrado status = 11                                │
├───────────────────────────────────────┼───────────┼─────────────────────────────────────────────────────────────────┤
│ match_status_14.csv                   │       1   │ match_geral filtrado status = 14                                │
├───────────────────────────────────────┼───────────┼─────────────────────────────────────────────────────────────────┤
│ not_match-somente-lado-caixa.csv      │      25   │ No Excel da CAIXA mas sem correspondência no SUHAB              │
├───────────────────────────────────────┼───────────┼─────────────────────────────────────────────────────────────────┤
│ not_match-somente-lado-suhab.csv      │     239   │ Status 15 no SUHAB mas CPF ausente nos Excel da CAIXA           │
└───────────────────────────────────────┴───────────┴─────────────────────────────────────────────────────────────────┘
```
