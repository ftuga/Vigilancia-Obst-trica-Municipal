"""Tests del silver — reglas 549 aplicadas + reconciliación DIVIPOLA.

Silver renombra cod_dpto_o/cod_mun_o del bronze a cod_dpto/cod_mpio canónicos.
Las reglas de exclusión (exterior, procedencia desconocida, muni desconocido)
se aplican durante build — aquí validamos el efecto post-build.
"""
from __future__ import annotations


def test_silver_no_exterior(con, silver_path):
    """Post-build: no hay filas con cod_dpto=1 (EXTERIOR)."""
    n = con.execute(f"SELECT COUNT(*) FROM '{silver_path}' WHERE cod_dpto = 1").fetchone()[0]
    assert n == 0, f"{n} filas con cod_dpto=1 (EXTERIOR) no debían estar"


def test_silver_no_procedencia_desconocida(con, silver_path):
    """Post-build: no hay filas con cod_dpto=0 (PROCEDENCIA DESCONOCIDA)."""
    n = con.execute(f"SELECT COUNT(*) FROM '{silver_path}' WHERE cod_dpto = 0").fetchone()[0]
    assert n == 0


def test_silver_no_muni_desconocido(con, silver_path):
    """Post-build: no hay filas con cod_mpio terminando en 000 (MUNICIPIO DESCONOCIDO)."""
    n = con.execute(f"SELECT COUNT(*) FROM '{silver_path}' WHERE cod_mpio % 1000 = 0").fetchone()[0]
    assert n == 0


def test_silver_conteo_positivo(con, silver_path):
    """El conteo de casos nunca debe ser negativo."""
    n = con.execute(f"SELECT COUNT(*) FROM '{silver_path}' WHERE conteo < 0").fetchone()[0]
    assert n == 0


def test_silver_cobertura_dpto(con, silver_path):
    """Silver debe cubrir ≥ 32 departamentos (de 33 DIVIPOLA + Bogotá)."""
    n = con.execute(f"SELECT COUNT(DISTINCT cod_dpto) FROM '{silver_path}'").fetchone()[0]
    assert n >= 32, f"Silver cubre solo {n} departamentos"


def test_silver_cobertura_muni(con, silver_path):
    """Silver debe cubrir ≥ 1.100 municipios distintos (de 1.122 DIVIPOLA)."""
    n = con.execute(f"SELECT COUNT(DISTINCT cod_mpio) FROM '{silver_path}'").fetchone()[0]
    assert n >= 1100, f"Silver cubre solo {n} municipios"
