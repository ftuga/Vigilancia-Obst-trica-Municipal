"""CLI para training C3. Thin wrapper sobre `mme.orchestration.train_c3`."""
from __future__ import annotations

from datetime import UTC, datetime

import typer

from mme.config import Config
from mme.orchestration import train_c3 as orch

app = typer.Typer(help="Entrenamiento del modelo C3 vulnerabilidad municipal MME.")


@app.command()
def train_c3(
    dataset_cycle: str = typer.Option(
        datetime.now(UTC).strftime("%Y-%m-%d"),
        "--dataset-cycle", "-d",
        help="Identificador de ciclo (ISO date).",
    ),
    n_trials: int = typer.Option(
        100, "--n-trials", "-t",
        help="Optuna trials para LightGBM.",
    ),
    no_mlflow: bool = typer.Option(
        False, "--no-mlflow",
        help="Deshabilita logging a MLflow (útil para smoke tests locales).",
    ),
) -> None:
    """Entrena NegBin GLM + LightGBM Poisson (Optuna) y persiste reporte."""
    cfg = Config()
    cfg.training.optuna_n_trials = n_trials
    typer.echo(
        f"[train-c3] cycle={dataset_cycle} trials={n_trials} mlflow={not no_mlflow}",
    )
    report = orch.run(
        config=cfg, dataset_cycle=dataset_cycle, mlflow_enabled=not no_mlflow,
    )
    path = orch.persist_report(report)
    typer.echo(f"[train-c3] reporte -> {path}")
    for r in report.results:
        typer.echo(
            f"  {r.family:<20} test: spearman_dpto={r.test_metrics.spearman_dpto} "
            f"MAE={r.test_metrics.mae_razon} p@50={r.test_metrics.precision_at_50}",
        )
    if report.mlflow_run_ids:
        typer.echo(f"[train-c3] mlflow runs: {report.mlflow_run_ids}")


if __name__ == "__main__":
    app()
