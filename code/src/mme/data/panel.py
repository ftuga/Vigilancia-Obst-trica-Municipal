"""Carga del panel gold MME + split temporal estricto.

Panel fuente: ``data/mme/gold/panel_muni_semestre.parquet`` (15.708 filas).
Split: train ≤2020 / val 2021 / test 2022 (no-negociable, metodología epidemiológica).
"""
from __future__ import annotations

from dataclasses import dataclass

import duckdb
import numpy as np
import pandas as pd

from mme.data.clayton_kaldor import ClaytonKaldorParams, empirical_bayes_smooth
from mme.paths import MME_DATA

GOLD_PATH = MME_DATA / "gold" / "panel_muni_semestre.parquet"

SPLIT_YEAR_TRAIN_MAX = 2020
SPLIT_YEAR_VAL = 2021
SPLIT_YEAR_TEST = 2022


@dataclass(frozen=True)
class PanelSplit:
    """Contiene los 3 splits temporales + metadata de preprocesamiento."""

    train: pd.DataFrame
    val: pd.DataFrame
    test: pd.DataFrame
    clayton_kaldor: ClaytonKaldorParams

    @property
    def n_train(self) -> int:
        """Filas de entrenamiento."""
        return len(self.train)

    @property
    def n_val(self) -> int:
        """Filas de validación."""
        return len(self.val)

    @property
    def n_test(self) -> int:
        """Filas de test."""
        return len(self.test)


def load_panel() -> pd.DataFrame:
    """Carga el gold panel municipio-semestre.

    Returns:
        DataFrame con las 69 columnas del contrato features-spec-v1 + columnas
        derivadas: ``pop_sem``, ``log_offset``, ``razon_obs``, ``razon_ck_eb``.

    Raises:
        FileNotFoundError: si el gold parquet no existe (correr DAG 1 primero).
    """
    if not GOLD_PATH.exists():
        raise FileNotFoundError(
            f"Gold panel no encontrado en {GOLD_PATH}. "
            "Ejecutar DAG `1-mme_etl_medallion` primero."
        )
    con = duckdb.connect(":memory:")
    df = con.execute(f"SELECT * FROM parquet_scan('{GOLD_PATH}')").df()
    con.close()
    # Drop muni sin población (offset indefinido)
    df = df[df["poblacion_total_2018"].notna() & (df["poblacion_total_2018"] > 0)].copy()
    df["pop_sem"] = df["poblacion_total_2018"] / 2.0
    df["log_offset"] = np.log(df["pop_sem"].clip(lower=1))
    df["razon_obs"] = df["casos_mme"] * 1000.0 / df["pop_sem"]
    return df


def split_temporal(df: pd.DataFrame) -> PanelSplit:
    """Split temporal estricto + Clayton-Kaldor EB global.

    Args:
        df: Panel cargado con ``load_panel()``.

    Returns:
        PanelSplit con train/val/test + params EB globales (fit sobre todo el panel
        para no leakear info entre splits — los parámetros son globales del país).
    """
    razon_ck, params = empirical_bayes_smooth(
        df["casos_mme"].to_numpy(),
        df["pop_sem"].to_numpy(),
    )
    df = df.copy()
    df["razon_ck_eb"] = razon_ck

    train = df[df["ano"] <= SPLIT_YEAR_TRAIN_MAX].copy()
    val = df[df["ano"] == SPLIT_YEAR_VAL].copy()
    test = df[df["ano"] == SPLIT_YEAR_TEST].copy()
    return PanelSplit(train=train, val=val, test=test, clayton_kaldor=params)
