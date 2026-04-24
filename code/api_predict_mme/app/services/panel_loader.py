"""Carga del panel gold + aplicación de PCA, con cache TTL en memoria.

El panel gold se actualiza semanalmente (DAG 1). No hace sentido re-leer
del filesystem en cada request. Cache con invalidación manual vía
``invalidate()`` (usado por ``POST /model/reload``).
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass

import pandas as pd
from mme.data.feature_set import apply_pca, load_feature_set, select_features
from mme.data.panel import load_panel

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PanelSnapshot:
    """Panel cacheado con timestamp."""

    panel: pd.DataFrame
    loaded_at: float
    n_rows: int
    years_available: list[int]
    feature_spec_version: str
    feature_names: list[str]


class PanelCache:
    """Cache thread-safe del panel gold + feature_set ya aplicado."""

    def __init__(self, ttl_seconds: int = 3600) -> None:
        self._ttl = ttl_seconds
        self._lock = threading.RLock()
        self._snapshot: PanelSnapshot | None = None

    def _is_expired(self, snap: PanelSnapshot) -> bool:
        return (time.time() - snap.loaded_at) > self._ttl

    def get(self) -> PanelSnapshot:
        """Retorna snapshot vigente; (re)carga si está expirado o ausente."""
        with self._lock:
            if self._snapshot is None or self._is_expired(self._snapshot):
                self._snapshot = self._load_fresh()
            return self._snapshot

    def invalidate(self) -> None:
        """Fuerza recarga en el próximo ``get()``."""
        with self._lock:
            self._snapshot = None

    def _load_fresh(self) -> PanelSnapshot:
        """Carga panel gold + aplica PCA."""
        fs = load_feature_set()
        panel = apply_pca(load_panel(), fs)
        years = sorted({int(y) for y in panel["ano"].unique()})
        snapshot = PanelSnapshot(
            panel=panel,
            loaded_at=time.time(),
            n_rows=len(panel),
            years_available=years,
            feature_spec_version=fs.version,
            feature_names=fs.features_final,
        )
        logger.info(
            "Panel cache loaded: %d rows, years=%s, fs_version=%s",
            len(panel), years, fs.version,
        )
        return snapshot


def filter_municipio(
    panel: pd.DataFrame,
    cod_mpio: str,
    feature_names: list[str],
    anio: int | None = None,
) -> pd.DataFrame:
    """Filtra el panel por municipio (y año si se especifica).

    Si el panel es semestre-granular, agrega por promedio dentro del año
    seleccionado. Retorna un DataFrame de 1 fila con las features finales.
    """
    df = panel[panel["cod_mpio"].astype(str).str.zfill(5) == cod_mpio]
    if df.empty:
        msg = f"cod_mpio '{cod_mpio}' no existe en el panel"
        raise KeyError(msg)
    if anio is not None:
        df = df[df["ano"] == anio]
        if df.empty:
            msg = f"cod_mpio '{cod_mpio}' sin datos para año {anio}"
            raise KeyError(msg)
    # Default: último año disponible para este muni (datos más recientes)
    if anio is None:
        anio = int(df["ano"].max())
        df = df[df["ano"] == anio]
    # Si hay ambos semestres en el año, promedio para obtener una row
    if len(df) > 1:
        df = df.groupby("cod_mpio", as_index=False).mean(numeric_only=True)
    return select_features(df, feature_names)


def filter_departamento(
    panel: pd.DataFrame,
    departamento_cod: str | None,
    feature_names: list[str],
    anio: int | None = None,
) -> pd.DataFrame:
    """Filtra panel por departamento (o todos) y retorna filas agregadas por muni.

    Útil para ``/predict/ranking``: retorna una fila por municipio con
    features listas para predecir.
    """
    df = panel.copy()
    if departamento_cod is not None:
        df = df[df["cod_dpto"].astype(str).str.zfill(2) == departamento_cod]
    if df.empty:
        msg = f"departamento_cod '{departamento_cod}' no existe en el panel"
        raise KeyError(msg)
    if anio is None:
        anio = int(df["ano"].max())
    df = df[df["ano"] == anio]
    if df.empty:
        msg = f"sin datos para departamento={departamento_cod} anio={anio}"
        raise KeyError(msg)
    # Agregado por muni: nombres se preservan vía first(), métricas vía mean.
    # groupby.mean(numeric_only=True) ignora cols de texto, por eso necesitamos
    # un merge con los nombres después.
    keys = ["cod_mpio", "cod_dpto"]
    nombres = (
        df[["cod_mpio", "cod_dpto", "nom_mpio", "nom_dpto"]]
        .drop_duplicates(subset=keys)
        if {"nom_mpio", "nom_dpto"}.issubset(df.columns)
        else None
    )
    df_grp = df.groupby(keys, as_index=False).mean(numeric_only=True)
    features = select_features(df_grp, feature_names)
    # cod_mpio/cod_dpto vuelven a int — groupby.mean los convierte a float
    features.insert(0, "cod_mpio", df_grp["cod_mpio"].astype(int).to_numpy())
    features.insert(1, "cod_dpto", df_grp["cod_dpto"].astype(int).to_numpy())
    if nombres is not None:
        nombres = nombres.assign(
            cod_mpio=nombres["cod_mpio"].astype(int),
            cod_dpto=nombres["cod_dpto"].astype(int),
        )
        features = features.merge(nombres, on=keys, how="left")
    features["_anio"] = anio
    return features
