"use server";

/**
 * Server actions para consumir api_predict_mme.
 *
 * La URL del backend vive solo server-side (API_PREDICT_MME_URL), nunca
 * llega al browser. Todas las llamadas pasan por estas funciones.
 */

const API_URL = process.env.API_PREDICT_MME_URL ?? "http://localhost:8001";

const REVALIDATE_MODEL_INFO_SECONDS = 300;
const REVALIDATE_RANKING_SECONDS = 600;

export interface RankingItemRaw {
  cod_mpio: string;
  nom_mpio?: string | null;
  departamento_cod: string;
  nom_dpto?: string | null;
  casos_mme_predichos: number;
  razon_mme_por_1000: number;
  ci_low: number;
  ci_high: number;
  risk_tier: "alto" | "medio" | "bajo";
}

export interface ModelInfo {
  registered_model_name: string;
  version: string;
  run_id: string;
  family: string;
  test_spearman_dpto: number;
  test_precision_at_50: number;
  dataset_cycle: string;
  feature_spec_version: string;
  n_features: number;
  residuals_available: boolean;
  baseline_available: boolean;
}

export interface RankingItem {
  cod_mpio: string;
  nom_mpio?: string | null;
  departamento_cod: string;
  nom_dpto?: string | null;
  casos_mme_predichos: number;
  razon_mme_por_1000: number;
  ci_low: number;
  ci_high: number;
  risk_tier: "alto" | "medio" | "bajo";
}

export interface PredictResponse extends RankingItem {
  anio: number;
  ci_level: number;
  n_bootstrap: number;
  feature_spec_version: string;
}

export async function getModelInfo(): Promise<ModelInfo | null> {
  try {
    const r = await fetch(`${API_URL}/model/info`, {
      next: { revalidate: REVALIDATE_MODEL_INFO_SECONDS },
    });
    if (!r.ok) return null;
    return (await r.json()) as ModelInfo;
  } catch {
    return null;
  }
}

export async function getRanking(
  departamento?: string,
  topN = 10,
): Promise<RankingItem[]> {
  const params = new URLSearchParams({ top_n: String(topN) });
  if (departamento) params.set("departamento", departamento);
  try {
    const r = await fetch(
      `${API_URL}/predict/ranking?${params.toString()}`,
      { next: { revalidate: REVALIDATE_RANKING_SECONDS } },
    );
    if (!r.ok) return [];
    return (await r.json()) as RankingItem[];
  } catch {
    return [];
  }
}

export async function getPredict(
  cod_mpio: string,
  anio?: number,
): Promise<PredictResponse | null> {
  try {
    const r = await fetch(`${API_URL}/predict/municipio`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ cod_mpio, anio }),
      cache: "no-store",
    });
    if (!r.ok) return null;
    return (await r.json()) as PredictResponse;
  } catch {
    return null;
  }
}

export interface TemporalPoint {
  anio: number;
  casos_mme_predichos: number;
  razon_mme_por_1000: number;
  ci_low: number;
  ci_high: number;
  risk_tier: "alto" | "medio" | "bajo";
  available: boolean;
}

export interface MuniDetail {
  cod_mpio: string;
  departamento_cod: string;
  latest: PredictResponse | null;
  serie: TemporalPoint[];
}

const ANIOS_SERIE = [2016, 2017, 2018, 2019, 2020, 2021, 2022] as const;

export async function getMuniDetail(cod_mpio: string): Promise<MuniDetail> {
  const responses = await Promise.all(
    ANIOS_SERIE.map(async (anio) => {
      const r = await getPredict(cod_mpio, anio);
      return { anio, response: r };
    }),
  );

  const serie: TemporalPoint[] = responses.map(({ anio, response }) =>
    response
      ? {
          anio,
          casos_mme_predichos: response.casos_mme_predichos,
          razon_mme_por_1000: response.razon_mme_por_1000,
          ci_low: response.ci_low,
          ci_high: response.ci_high,
          risk_tier: response.risk_tier,
          available: true,
        }
      : {
          anio,
          casos_mme_predichos: 0,
          razon_mme_por_1000: 0,
          ci_low: 0,
          ci_high: 0,
          risk_tier: "bajo" as const,
          available: false,
        },
  );

  const latest = [...responses]
    .reverse()
    .find((x) => x.response !== null)?.response ?? null;

  const departamento_cod = latest?.departamento_cod ?? cod_mpio.slice(0, 2);

  return {
    cod_mpio,
    departamento_cod,
    latest,
    serie,
  };
}

export async function pingHealth(): Promise<{
  healthz: boolean;
  readyz: boolean;
  details: Record<string, unknown>;
}> {
  const [h, r] = await Promise.all([
    fetch(`${API_URL}/healthz`, { cache: "no-store" }).then((x) => x.ok).catch(() => false),
    fetch(`${API_URL}/readyz`, { cache: "no-store" })
      .then(async (x) => (x.ok ? ((await x.json()) as { details: Record<string, unknown> }) : null))
      .catch(() => null),
  ]);
  return {
    healthz: h,
    readyz: r !== null,
    details: r?.details ?? {},
  };
}
