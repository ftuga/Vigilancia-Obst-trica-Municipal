import Link from "next/link";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { getModelInfo } from "./api-actions";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  const info = await getModelInfo();

  return (
    <div className="space-y-12 pb-8">
      {/* Hero */}
      <section className="space-y-4">
        <h1 className="text-3xl font-semibold tracking-tight md:text-4xl">
          Vigilancia Obstétrica Municipal
        </h1>
        <p className="max-w-3xl text-base leading-relaxed text-muted-foreground">
          Sistema de predicción de <strong>vulnerabilidad obstétrica a nivel
          municipal</strong> en Colombia. Cruza la notificación de{" "}
          <strong>Morbilidad Materna Extrema (MME)</strong> de SIVIGILA con
          determinantes sociales (NBI Censo 2018), capacidad obstétrica (REPS),
          afiliación al sistema de salud (BDUA) y población DANE para producir,
          a nivel municipal y semestre por semestre, una predicción del número
          esperado de casos MME.
        </p>
        <div className="flex flex-wrap gap-3 pt-2">
          <Link
            href="/mme"
            className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90"
          >
            Ver mapa y ranking
          </Link>
          <Link
            href="/mme/explorar"
            className="rounded-md border border-border px-4 py-2 text-sm font-medium hover:bg-muted"
          >
            Explorar todos los municipios
          </Link>
          <Link
            href="/health"
            className="rounded-md border border-border px-4 py-2 text-sm font-medium hover:bg-muted"
          >
            Estado del servicio
          </Link>
        </div>
      </section>

      {/* Estado del modelo */}
      {info && (
        <section className="grid gap-3 rounded-lg border bg-muted/30 p-4 sm:grid-cols-4">
          <Stat label="Modelo en producción" value={`v${info.version}`} sub={info.family} />
          <Stat
            label="Spearman departamental"
            value={info.test_spearman_dpto.toFixed(3)}
            sub="test 2022"
          />
          <Stat
            label="Precision @ top-50"
            value={info.test_precision_at_50.toFixed(2)}
            sub="acierto top-50 muni"
          />
          <Stat
            label="IC bootstrap"
            value={info.residuals_available ? "90% disponible" : "no disponible"}
            sub={info.residuals_available ? "200 replicates" : "champion sin residuos"}
          />
        </section>
      )}

      {/* Glosario */}
      <section className="space-y-4">
        <h2 className="text-xl font-semibold tracking-tight">Glosario</h2>
        <p className="text-sm text-muted-foreground">
          Términos técnicos del dashboard, en orden de aparición.
        </p>
        <div className="grid gap-4 md:grid-cols-2">
          <Glossary title="Morbilidad Materna Extrema (MME)">
            Complicación severa del embarazo, parto o puerperio que casi causa
            la muerte de la gestante. En Colombia se notifica obligatoriamente
            a SIVIGILA bajo el código de evento <strong>549</strong>. Es un
            indicador centinela de la calidad de la atención obstétrica.
          </Glossary>
          <Glossary title="SIVIGILA">
            Sistema Nacional de Vigilancia en Salud Pública (INS · MinSalud).
            Recibe notificación obligatoria semanal de eventos de interés. La
            cobertura no es uniforme entre municipios; existen{" "}
            <em>silentes</em> (muni que no notifican) que sub-estiman el
            denominador real.
          </Glossary>
          <Glossary title="Razón MME × 1.000 hab.">
            Número esperado de casos de MME por cada 1.000 habitantes en el
            semestre. Es la métrica principal del dashboard. No confundir con
            la razón × 100.000 nacidos vivos (NV) usada en reportes
            internacionales — son escalas distintas.
          </Glossary>
          <Glossary title="Vulnerabilidad obstétrica municipal">
            Predicción del modelo C3: cuántos casos MME se esperan en un
            municipio dado, en función de sus determinantes (NBI, ruralidad,
            capacidad obstétrica, etc.). Es una propiedad{" "}
            <em>territorial</em>, no individual.
          </Glossary>
          <Glossary title="DIVIPOLA">
            Codificación oficial DANE de la división político-administrativa
            colombiana. Departamento = 2 dígitos, municipio = 5 dígitos
            (incluye los del depto).{" "}
            <code className="rounded bg-muted px-1 py-0.5 text-xs">05001</code>{" "}
            es Medellín (Antioquia, depto 05).
          </Glossary>
          <Glossary title="NBI">
            Necesidades Básicas Insatisfechas (Censo 2018). Indicador
            multidimensional de pobreza estructural por hogar (vivienda,
            servicios, hacinamiento, dependencia, escolaridad). El modelo usa
            las componentes principales (PCA) del bloque NBI como predictor.
          </Glossary>
        </div>
      </section>

      {/* Cómo se construye la predicción */}
      <section className="space-y-4">
        <h2 className="text-xl font-semibold tracking-tight">
          Cómo se construye la predicción
        </h2>
        <div className="grid gap-4 md:grid-cols-3">
          <StepCard
            n="1"
            title="Datos"
            body="SIVIGILA 549 (notificación MME) + NBI Censo 2018 + REPS + BDUA + población DANE. Pipeline Airflow bronze→silver→gold sobre DuckDB."
          />
          <StepCard
            n="2"
            title="Modelo C3"
            body="LightGBM con objetivo Poisson (counts no-negativos) + offset poblacional. Optuna con TPE selecciona hiperparámetros. NegBin GLM como baseline interpretable."
          />
          <StepCard
            n="3"
            title="Servicio"
            body="API FastAPI sirve el champion del MLflow Registry. Por cada predicción agrega un IC 90% por bootstrap residual cuando hay residuos disponibles."
          />
        </div>
      </section>

      {/* Cómo leer las visualizaciones */}
      <section className="space-y-4">
        <h2 className="text-xl font-semibold tracking-tight">
          Cómo leer las visualizaciones
        </h2>
        <div className="grid gap-4 md:grid-cols-2">
          <ReadingCard
            title="Bar chart de departamentos"
            body="Cada barra es el promedio de la razón MME predicha sobre los muni del top-N en ese departamento. El color indica el tier de riesgo del promedio. No representa el departamento completo si hay muni excluidos."
          />
          <ReadingCard
            title="Tier de riesgo (color)"
            body={
              <div className="space-y-1.5">
                <div className="flex items-center gap-2">
                  <Badge variant="alto">alto</Badge>
                  <span>razón ≥ 1.5 × 1.000 hab</span>
                </div>
                <div className="flex items-center gap-2">
                  <Badge variant="medio">medio</Badge>
                  <span>razón ≥ 0.8 y &lt; 1.5</span>
                </div>
                <div className="flex items-center gap-2">
                  <Badge variant="bajo">bajo</Badge>
                  <span>razón &lt; 0.8</span>
                </div>
                <p className="pt-1 text-xs text-muted-foreground">
                  Umbrales calibrados sobre la distribución observada del
                  modelo C3.
                </p>
              </div>
            }
          />
          <ReadingCard
            title="IC 90% — Intervalo de Confianza bootstrap"
            body="Banda alrededor de la predicción puntual. Se construye remuestreando con reemplazo los residuos de entrenamiento (bootstrap residual, 200 replicates). Cuando aparece como `—`, el champion no tiene residuos adjuntos: la predicción es puntual sin estimación de incertidumbre."
          />
          <ReadingCard
            title="Spearman departamental (ρ)"
            body="Correlación de rangos entre la razón MME real y la predicha, agregando muni al departamento. Robusta a la falacia ecológica. ρ=0.834 indica que el modelo ordena bien los departamentos por riesgo, aunque los valores absolutos a nivel muni puedan tener mayor error."
          />
          <ReadingCard
            title="Precision @ top-50"
            body="De los 50 muni que el modelo identifica como de mayor riesgo, qué fracción está realmente en el top-50 observado. Métrica de utilidad operativa: prioriza acierto en la cola alta más que error global."
          />
          <ReadingCard
            title="Serie temporal (página de muni)"
            body="Predicción por año 2016–2022. La banda alrededor de la línea es el IC 90%. Permite identificar si la vulnerabilidad cambió en el tiempo (ej. efecto COVID), si el modelo es estable o si hay años con datos faltantes."
          />
        </div>
      </section>

      {/* Disclaimer destacado */}
      <section>
        <Card className="border-amber-200 bg-amber-50/50">
          <CardHeader>
            <CardTitle className="text-base text-amber-900">
              Importante: falacia ecológica
            </CardTitle>
            <CardDescription className="text-amber-900/80">
              El modelo opera a nivel municipal — predice cuántos casos MME se
              esperan en un territorio. No predice el riesgo individual de una
              gestante. Un municipio &quot;alto&quot; no implica que toda
              gestante en ese municipio tenga riesgo alto, ni viceversa. Usar
              para priorización territorial, no para decisiones clínicas
              individuales. Ver{" "}
              <code className="rounded bg-amber-100 px-1 py-0.5">
                docs/mme/model-evaluation.md §3
              </code>
              .
            </CardDescription>
          </CardHeader>
        </Card>
      </section>
    </div>
  );
}

function Stat({
  label,
  value,
  sub,
}: {
  label: string;
  value: string;
  sub: string;
}) {
  return (
    <div>
      <p className="text-xs uppercase tracking-wide text-muted-foreground">
        {label}
      </p>
      <p className="mt-1 text-xl font-semibold tabular-nums">{value}</p>
      <p className="text-xs text-muted-foreground">{sub}</p>
    </div>
  );
}

function Glossary({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-semibold">{title}</CardTitle>
      </CardHeader>
      <CardContent className="text-sm leading-relaxed text-muted-foreground">
        {children}
      </CardContent>
    </Card>
  );
}

function StepCard({
  n,
  title,
  body,
}: {
  n: string;
  title: string;
  body: string;
}) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-center gap-2">
          <span className="flex h-6 w-6 items-center justify-center rounded-full bg-primary text-xs font-semibold text-primary-foreground">
            {n}
          </span>
          <CardTitle className="text-sm">{title}</CardTitle>
        </div>
      </CardHeader>
      <CardContent className="text-sm leading-relaxed text-muted-foreground">
        {body}
      </CardContent>
    </Card>
  );
}

function ReadingCard({
  title,
  body,
}: {
  title: string;
  body: React.ReactNode;
}) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-semibold">{title}</CardTitle>
      </CardHeader>
      <CardContent className="text-sm leading-relaxed text-muted-foreground">
        {body}
      </CardContent>
    </Card>
  );
}
