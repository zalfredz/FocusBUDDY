# Experiment Reports

File di folder ini adalah hasil eksperimen reproducible, bukan klaim bahwa model
siap produksi. `duration_baseline.*` dibuat oleh:

```bash
PYTHONPATH="$PWD" ~/.venvs/focusbuddy/bin/python -m ml.experiments.duration_baseline
```

Phase 7 menghasilkan:

- `real_user_data_readiness.json`;
- `personalization_readiness.json`;
- `personalization_evaluation.json` hanya jika temporal holdout nyata cukup.

Report Phase 7 yang ada saat ini berasal dari fixture sintetis untuk validasi
pipeline. Field `audited_input.scope` membedakannya dari restricted Supabase
export; angka di report tidak boleh dianggap sebagai query database live.

Evaluasi retrieval PECAH TUGAS menghasilkan
`task_decomposition_retrieval_eval.json` melalui:

```bash
PYTHONPATH="$PWD" ~/.venvs/focusbuddy/bin/python tools/evaluate_retrieval.py
```

Laporan ini mengukur corpus Indonesia terhadap query exact, paraphrase, dan
negative. Ia adalah benchmark correctness retrieval, bukan artefak training.
