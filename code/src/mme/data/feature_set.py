"""Carga del feature_set_v1 + aplicación del pipeline PCA persistido."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from mme.paths import MME_REPORTS

FEATURE_SET_PATH = MME_REPORTS / "models" / "feature_set_v1.json"


@dataclass(frozen=True)
class FeatureSet:
    """Representación del feature_set_v1 persistido."""

    version: str
    features_final: list[str]
    features_original: list[str]
    features_pca: list[str]
    pca_input_features: list[str]
    pca_scaler_mean: np.ndarray
    pca_scaler_scale: np.ndarray
    pca_components: np.ndarray
    pca_new_names: list[str]
    raw: dict[str, Any]


def load_feature_set(path: Path = FEATURE_SET_PATH) -> FeatureSet:
    """Carga el feature_set_v1.json generado por feature_selection_c3.

    Args:
        path: Ruta al JSON persistido. Default: reports/mme/models/feature_set_v1.json.

    Returns:
        FeatureSet estructurado.

    Raises:
        FileNotFoundError: si el JSON no existe (correr feature_selection primero).
    """
    if not path.exists():
        raise FileNotFoundError(
            f"feature_set no encontrado en {path}. "
            "Ejecutar `scripts/mme/feature_selection_c3.py` primero."
        )
    data = json.loads(path.read_text())
    pca_block = data["pipeline"]["pca_block"]
    return FeatureSet(
        version=data["version"],
        features_final=data["features_final"],
        features_original=data["features_original"],
        features_pca=data["features_pca"],
        pca_input_features=pca_block["input_features"],
        pca_scaler_mean=np.asarray(pca_block["scaler_mean"]),
        pca_scaler_scale=np.asarray(pca_block["scaler_scale"]),
        pca_components=np.asarray(pca_block["pca_components"]),
        pca_new_names=pca_block["new_feature_names"],
        raw=data,
    )


def apply_pca(df: pd.DataFrame, fs: FeatureSet) -> pd.DataFrame:
    """Aplica el pipeline scaler+PCA del bloque NBI.

    Args:
        df: DataFrame con las features originales (al menos las de NBI).
        fs: FeatureSet cargado con ``load_feature_set()``.

    Returns:
        Copia de ``df`` con las columnas PCA agregadas (``nbi_pc1``, etc.).
    """
    out = df.copy()
    nbi = out[fs.pca_input_features].copy()
    for col in fs.pca_input_features:
        median = nbi[col].median()
        fill = 0.0 if pd.isna(median) else float(median)
        nbi[col] = nbi[col].fillna(fill)
    scale = np.where(fs.pca_scaler_scale > 0, fs.pca_scaler_scale, 1.0)
    z = (nbi.to_numpy() - fs.pca_scaler_mean) / scale
    pcs = z @ fs.pca_components.T
    for i, name in enumerate(fs.pca_new_names):
        out[name] = pcs[:, i]
    return out


def select_features(df: pd.DataFrame, features: list[str]) -> pd.DataFrame:
    """Selecciona subset de features con fill NaN → mediana.

    Args:
        df: DataFrame origen con (al menos) las columnas de ``features``.
        features: Lista de columnas a retener.

    Returns:
        DataFrame copia con solo las columnas de interés y sin NaN.
    """
    out = df[features].copy()
    for col in features:
        if not out[col].isna().any():
            continue
        median = out[col].median()
        fill = 0.0 if pd.isna(median) else float(median)
        out[col] = out[col].fillna(fill)
    return out
