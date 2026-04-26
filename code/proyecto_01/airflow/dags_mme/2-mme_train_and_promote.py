"""
DAG 2-mme_train_and_promote — entrenamiento C3 + promoción a Registry.

Pipeline semanal de modelado:
  1. check_drift        (Evidently + PSI/KS; gate si no-drift ∧ champion vigente)
  2. train_c3           (4 familias: poisson, negbin, lgbm_tweedie, lgbm_razon)
  3. validate_report    (assert criterios Go/No-Go)
  4. promote_c3         (champion/challenger → Registry mme_vulnerability_baseline)

Depende de DAG 1-mme_etl_medallion (gold panel actualizado).

Schedule: @weekly Lunes 04:00 UTC. Manual trigger OK (ShortCircuit evita re-train innecesario).
"""
from __future__ import annotations

import os
import subprocess
from datetime import timedelta
from pathlib import Path
from typing import Any

import pendulum
from airflow.decorators import dag, task

try:
    from _callbacks import on_failure_callback
except ImportError:
    on_failure_callback = None


REPO_ROOT = "/opt/repo"
DATA_MME = "/opt/airflow/data/mme"

SCRIPT_ENV = {
    **os.environ,
    "MME_DATA_ROOT": DATA_MME,
    "MME_REPORTS_ROOT": f"{DATA_MME}/reports",
    # PYTHONPATH incluye scripts/mme (legacy _paths) + src (paquete refactorizado)
    "PYTHONPATH": f"{REPO_ROOT}/src:{REPO_ROOT}/scripts/mme",
    "MLFLOW_TRACKING_URI": os.environ.get("MLFLOW_TRACKING_URI", "http://mlflow:5000"),
    "PUSHGATEWAY_URL": os.environ.get("PUSHGATEWAY_URL", "pushgateway:9091"),
}


def _run_script(script: str, extra_args: list[str] | None = None, timeout: int = 3600) -> str:
    """Legacy: ejecuta un script en scripts/mme/. Solo para ingesta no migrada."""
    cmd = ["python", f"{REPO_ROOT}/scripts/mme/{script}"]
    if extra_args:
        cmd.extend(extra_args)
    r = subprocess.run(cmd, capture_output=True, text=True, env=SCRIPT_ENV,
                       cwd=DATA_MME, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(
            f"{script} failed rc={r.returncode}\nstdout:\n{r.stdout[-2000:]}\n"
            f"stderr:\n{r.stderr[-2000:]}"
        )
    return r.stdout


def _run_module(module: str, args: list[str], timeout: int = 3600) -> str:
    """Ejecuta un entry point del paquete `mme` refactorizado.

    Usa `python -m module` contra PYTHONPATH que incluye /opt/repo/src.
    Preferred sobre _run_script para código nuevo post-refactor (src/mme/).
    """
    cmd = ["python", "-m", module, *args]
    r = subprocess.run(cmd, capture_output=True, text=True, env=SCRIPT_ENV,
                       cwd=DATA_MME, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(
            f"python -m {module} failed rc={r.returncode}\n"
            f"stdout:\n{r.stdout[-2000:]}\nstderr:\n{r.stderr[-2000:]}"
        )
    return r.stdout


default_args = {
    "owner": "mme",
    "depends_on_past": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=15),
    "on_failure_callback": on_failure_callback,
}


@dag(
    dag_id="2-mme_train_and_promote",
    description="Entrenamiento C3 vulnerabilidad municipal + promoción MLflow Registry",
    schedule="0 4 * * *",  # diario 04:00 UTC (2h después del DAG 1)
    start_date=pendulum.datetime(2026, 4, 23, tz="UTC"),
    catchup=False,
    max_active_runs=1,
    dagrun_timeout=timedelta(hours=3),
    default_args=default_args,
    tags=["mme", "ml", "c3", "training"],
)
def mme_train_and_promote():

    @task(task_id="check_drift")
    def check_drift() -> dict[str, Any]:
        """Chequeo de drift del gold panel vs champion vigente (Evidently+PSI/KS).

        Flujo:
          1. Cargar baseline artifact del champion (``drift/baseline.parquet``).
          2. Si no hay champion o no hay baseline → drift_detected=True (retrain).
          3. Si hay → construir current (panel actual post-PCA, misma lista de
             features que baseline) y correr ``run_drift_check``.
          4. Publicar PSI/KS al Pushgateway y devolver flags.

        Gate downstream: ``gate_train`` pasa si ``drift_detected or
        no_champion``.
        """
        import sys
        sys.path.insert(0, f"{REPO_ROOT}/src")
        from pathlib import Path as _Path

        from mme.config import Config
        from mme.data.feature_set import apply_pca, load_feature_set
        from mme.data.panel import load_panel
        from mme.drift.evidently_runner import run_drift_check
        from mme.tracking.mlflow_ops import load_champion_baseline
        from mme.tracking.pushgateway import push_drift_status

        cfg = Config()
        # 1. Baseline del champion
        baseline_df = load_champion_baseline("mme_vulnerability_baseline")
        if baseline_df is None or baseline_df.empty:
            print("[check_drift] sin baseline del champion — drift=True (retrain)")
            try:
                push_drift_status(drift_detected=True)
            except Exception as e:  # noqa: BLE001
                print(f"[check_drift] pushgateway falló (no-bloqueante): {e}")
            return {
                "status": "no_baseline",
                "drift_detected": True,
                "gate_train": True,
            }

        # 2. Construir current con mismas features que baseline
        feature_cols = list(baseline_df.columns)
        fs = load_feature_set()
        panel = apply_pca(load_panel(), fs)
        missing = [c for c in feature_cols if c not in panel.columns]
        if missing:
            print(f"[check_drift] features ausentes en panel actual: {missing}")
            return {
                "status": "schema_mismatch",
                "drift_detected": True,
                "gate_train": True,
                "missing": missing,
            }
        current_df = panel[feature_cols].copy()

        # 3. Drift check
        out_dir = _Path(DATA_MME) / "reports" / "drift"
        cycle = pendulum.now("UTC").strftime("%Y-%m-%d")
        report = run_drift_check(
            current_df=current_df,
            baseline_df=baseline_df,
            feature_cols=feature_cols,
            out_dir=out_dir,
            html_name=f"drift_{cycle}.html",
        )
        print(
            f"[check_drift] drift_detected={report.drift_detected} "
            f"features_drifted={report.features_drifted} "
            f"n_baseline={report.n_baseline} n_current={report.n_current}",
        )

        # 4. Push al Pushgateway
        try:
            push_drift_status(
                drift_detected=report.drift_detected,
                psi_by_feature=report.psi_by_feature,
                ks_by_feature=report.ks_stat_by_feature,
            )
        except Exception as e:  # noqa: BLE001
            print(f"[check_drift] pushgateway falló (no-bloqueante): {e}")

        return {
            "status": "checked",
            "drift_detected": report.drift_detected,
            "gate_train": report.drift_detected,
            "features_drifted": report.features_drifted,
            "n_features": len(feature_cols),
            "html": str(report.html_report_path) if report.html_report_path else None,
            "psi_max": max(report.psi_by_feature.values())
                if report.psi_by_feature else 0.0,
        }

    @task.short_circuit(task_id="gate_train")
    def gate_train(drift_info: dict) -> bool:
        """Skip entrenamiento si no hay drift Y hay champion vigente reciente."""
        return bool(drift_info.get("gate_train", True))

    @task(task_id="feature_selection")
    def feature_selection() -> str:
        """Re-ejecuta feature_selection_c3.py para refrescar feature_set_v1.json
        con los datos más recientes. Genera PCA pipeline persistido."""
        return _run_script("feature_selection_c3.py", timeout=600)

    @task(task_id="train_c3")
    def train_c3(_fs_output: str) -> str:
        """Entrena NegBin GLM + LightGBM(Optuna) sobre feature_set_v1.json.

        Usa el paquete refactorizado `mme.cli.train` (typer entry point).
        La lógica vive en `src/mme/` modularmente. El monolito legacy
        `scripts/mme/train_c3_v1.py` queda para borrar en cleanup post-migración.
        """
        dataset_cycle = pendulum.now("UTC").strftime("%Y-%m-%d")
        n_trials = int(os.environ.get("OPTUNA_N_TRIALS", "50"))
        return _run_module(
            "mme.cli.train",
            ["--dataset-cycle", dataset_cycle,
             "--n-trials", str(n_trials)],
            timeout=3600,
        )

    @task(task_id="validate_report")
    def validate_report(train_log: str) -> dict[str, Any]:
        """Lee el reporte JSON del último training y valida criterios Go/No-Go.

        Criterios (ml-problem-definition.md §6 + enriquecimiento P1):
        - Mejor test Spearman dpto ≥ 0.3.
        - Mejor test precision@top50 ≥ 0.08.
        - Overfit gap (|val_spearman - test_spearman|) ≤ 0.2 en el mejor modelo.
        - Mejor test r2_log_counts > 0 (modelo no-trivial).
        - mae_razon finito (no NaN/inf) en todos los runs.
        """
        import json
        from pathlib import Path
        reports_dir = Path(DATA_MME) / "reports" / "models"
        candidates = sorted(reports_dir.glob("train_c3_*.json"))
        if not candidates:
            raise AssertionError("no se encontró reporte train_c3_*.json tras train")
        latest = candidates[-1]
        data = json.loads(latest.read_text())
        results = data.get("results", [])
        if not results:
            raise AssertionError("reporte vacío — training no produjo runs")

        # Acumular métricas por familia
        test_rhos = []
        test_p50s = []
        best_idx = 0
        for i, r in enumerate(results):
            test_block = r.get("test") or {}
            rho = test_block.get("spearman_dpto") or 0
            p50 = test_block.get("precision_at_50") or 0
            test_rhos.append(rho)
            test_p50s.append(p50)
            if rho > test_rhos[best_idx]:
                best_idx = i
        best_rho = test_rhos[best_idx]
        best_p50 = max(test_p50s)
        best_family = results[best_idx].get("family", "unknown")
        best_test = results[best_idx].get("test") or {}
        best_val = results[best_idx].get("val") or {}

        # Push métricas a Pushgateway ANTES del gate — así Prometheus ve el fallo
        import sys
        sys.path.insert(0, f"{REPO_ROOT}/src")
        try:
            from mme.tracking.pushgateway import push_model_metrics
            push_model_metrics(data)
        except Exception as e:  # noqa: BLE001 — push no bloquea el gate
            print(f"[validate_report] pushgateway falló (no-bloqueante): {e}")

        # Gate 1: Spearman dpto ≥ 0.3
        if best_rho < 0.3:
            raise AssertionError(
                f"Gate falla: mejor test Spearman dpto = {best_rho:.3f} < 0.3",
            )
        # Gate 2: precision@50 ≥ 0.08
        if best_p50 < 0.08:
            raise AssertionError(
                f"Gate falla: mejor test precision@top50 = {best_p50:.3f} < 0.08",
            )
        # Gate 3: r2_log_counts > 0 (modelo no-trivial)
        best_r2 = best_test.get("r2_log_counts")
        if best_r2 is None or best_r2 <= 0:
            raise AssertionError(
                f"Gate falla: mejor test r2_log_counts = {best_r2} no es > 0",
            )
        # Gate 4: overfit gap val→test ≤ 0.2
        val_rho = best_val.get("spearman_dpto")
        if val_rho is not None:
            gap = abs(val_rho - best_rho)
            if gap > 0.2:
                raise AssertionError(
                    f"Gate falla: overfit gap val_spearman={val_rho:.3f} "
                    f"- test_spearman={best_rho:.3f} = {gap:.3f} > 0.2",
                )
        # Gate 5: mae_razon finito en todos los runs
        import math
        for r in results:
            mae = (r.get("test") or {}).get("mae_razon")
            if mae is None or not math.isfinite(mae):
                raise AssertionError(
                    f"Gate falla: mae_razon no-finito en {r.get('family')}: {mae}",
                )

        return {
            "best_family": best_family,
            "best_spearman_dpto": best_rho,
            "best_precision_at_50": best_p50,
            "best_r2_log_counts": best_r2,
            "overfit_gap": abs((val_rho or best_rho) - best_rho),
            "report": str(latest),
            "n_runs": len(results),
            "mlflow_run_ids": data.get("mlflow_run_ids", {}),
        }

    @task(task_id="promote_c3")
    def promote_c3(validation: dict) -> dict[str, Any]:
        """Promueve el mejor run del experimento a Registry via alias @champion.

        Gate combinado (``new >= prev*tolerance OR new >= absolute_floor``)
        implementado en ``mme.tracking.mlflow_ops.promote_champion``.

        Overrides opcionales vía Airflow Variables:
          - promote_tolerance (float, default 0.95)
          - promote_absolute_floor (float, default 0.65)
          - promote_dry_run (bool-ish, default false)
        """
        import sys
        sys.path.insert(0, f"{REPO_ROOT}/src")
        from airflow.models import Variable

        from mme.config import Config
        from mme.tracking.mlflow_ops import promote_champion

        cfg = Config()
        tolerance = float(Variable.get("promote_tolerance", default_var="0.95"))
        floor = float(Variable.get("promote_absolute_floor", default_var="0.65"))
        dry_run_raw = str(Variable.get("promote_dry_run", default_var="false")).lower()
        dry_run = dry_run_raw in ("1", "true", "yes", "on")

        decision = promote_champion(
            experiment_name=cfg.mlflow.experiment_name,
            registered_model_name="mme_vulnerability_baseline",
            tolerance=tolerance,
            absolute_floor=floor,
            dry_run=dry_run,
        )
        print(f"[promote_c3] decision={decision}")

        # Si no hubo candidatos MLflow (caso legacy: training sin mlflow_enabled),
        # no fallar: solo señalizar y retornar.
        if decision.reason == "no_candidates_found":
            return {
                "status": "no_candidates_in_mlflow",
                "promoted": False,
                "validation": validation,
            }

        # Gate fail es decisión válida: no lanzar error, solo reportar
        return {
            "status": "promoted" if decision.promoted else "rejected",
            "promoted": decision.promoted,
            "new_version": decision.new_version,
            "new_run_id": decision.new_run_id,
            "new_score": decision.new_score,
            "prev_version": decision.prev_version,
            "prev_score": decision.prev_score,
            "reason": decision.reason,
            "validation": validation,
        }

    # Wiring
    drift = check_drift()
    gate = gate_train(drift)
    fs = feature_selection()
    trained = train_c3(fs)
    validated = validate_report(trained)
    promoted = promote_c3(validated)

    gate >> fs >> trained >> validated >> promoted


mme_train_and_promote()
