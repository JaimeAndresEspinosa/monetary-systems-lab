# Monetary Systems Lab

Simulador de sistemas monetarios. Combina **reglas de emisión**, **canales del
dinero nuevo** y **sistemas bancarios**, y mide qué le pasa a una economía de
miles de hogares: inflación, paro, salarios, vivienda, deuda y, sobre todo,
**quién gana y quién pierde riqueza**.

El motor es un modelo **basado en agentes con contabilidad stock-flujo
consistente** (ABM-SFC): cada euro tiene origen y destino, y cada mes se
comprueba que los balances de todos los sectores cuadran.

## Qué hace

- **Laboratorio**: elige una pieza de cada dimensión (4 × 4 × 2 = 32 sistemas)
  y simula la economía con Monte Carlo (mediana y banda 10–90 %). Muestra
  24 indicadores, el reparto de la riqueza por decil (efecto Cantillon), por
  dónde entra el dinero nuevo y la matriz de balances y flujos.
- **Comparar**: hasta tres sistemas con la misma economía de partida y las
  mismas semillas.
- **Explorador**: las 32 combinaciones simuladas 10 veces cada una, ordenables,
  y el **efecto principal** de cada pieza sobre cada indicador.
- **Metodología**: agentes, contabilidad, ecuaciones, calibración, validación,
  limitaciones y referencias.

| Dimensión | Opciones |
|---|---|
| Regla de emisión | discrecional (Taylor + QE) · algoritmo del 2 % · patrón oro · oferta fija con halvings |
| Canal del dinero nuevo | bancos (compra de bonos) · gasto público · dividendo ciudadano · mineros/validadores |
| Sistema bancario | reserva fraccionaria · reserva del 100 % (Chicago Plan) |

## Primeros resultados (calibración base, 10 años, 10 simulaciones)

| Sistema | Inflación | Paro | Δ cuota del 10 % más rico | Bolsa real (inicio = 100) |
|---|---|---|---|---|
| Actual (discrecional · bancos · fraccionaria) | 2,6 % | 9,4 % | −1,1 pp | 133 |
| Patrón oro | 1,1 % | 9,1 % | −0,1 pp | 194 |
| Bitcoin como moneda (oferta fija · mineros · fraccionaria) | 0,5 % | 8,7 % | **+4,0 pp** | 307 |
| Chicago Plan (algoritmo 2 % · gasto público · reserva 100 %) | 4,2 % | 7,6 % | −2,3 pp | 132 |
| Algoritmo 2 % · dividendo · reserva 100 % | 3,7 % | 8,2 % | **−2,8 pp** | 160 |

Lectura: cuanto más escaso es el dinero, menor es la inflación, pero los
activos de los más ricos (empresas, vivienda) se revalorizan en términos reales
y su cuota de riqueza crece. Cuando el dinero nuevo entra directamente por los
hogares o por el gasto público sin crédito bancario, ocurre lo contrario, a
costa de algo más de inflación.

Con la regla discrecional y sin crisis, el banco central no llega a crear dinero
base (la inflación no baja del objetivo), así que el canal no cambia nada: todo
el dinero nuevo lo crean los bancos al prestar. Los canales se diferencian en
las crisis, que llegan con la Fase 2.

> Son resultados de un modelo con supuestos explícitos (ver Metodología), no
> predicciones. Lo relevante son las diferencias entre sistemas con la misma
> economía de partida.

## Cómo arrancarla

En Windows, doble clic en **`iniciar.bat`**. O a mano:

```bash
pip install -r requirements.txt
python -m uvicorn app:app --port 8000
```

y abre http://localhost:8000.

Tests (contabilidad de las 32 combinaciones, hechos estilizados, mecanismos):

```bash
pip install -r requirements-dev.txt
python -m pytest
```

Recalcular el explorador después de cambiar el modelo:

```bash
python scripts/build_grid.py --seeds 10
```

## Estructura

| Archivo | Contenido |
|---|---|
| `msl/config.py` | Catálogo de dimensiones y parámetros de la economía |
| `msl/economy.py` | Balances de los 5 sectores y asientos de doble entrada |
| `msl/model.py` | Agentes y comportamiento mes a mes |
| `msl/metrics.py` | Gini, cuotas y definición de los indicadores |
| `msl/experiments.py` | Monte Carlo y barrido de combinaciones |
| `app.py` | API FastAPI |
| `static/` | Web (HTML, CSS y JavaScript sin dependencias; gráficos SVG propios) |
| `data/grid.json` | Resultados precalculados del explorador |
| `tests/` | Tests de contabilidad y de comportamiento |

### API

| Endpoint | Devuelve |
|---|---|
| `GET /api/catalog` | Dimensiones, opciones, indicadores y parámetros por defecto |
| `POST /api/simulate` | Monte Carlo de un sistema: series con bandas, resumen, deciles, balances y flujos |
| `GET /api/grid` | Las 32 combinaciones precalculadas |

## Publicarla

Igual que Magic Formula: sube la carpeta a GitHub y en Render crea un
*Blueprint* con `render.yaml` (o un *Web Service* con build
`pip install -r requirements.txt` y start `uvicorn app:app --host 0.0.0.0 --port $PORT`).

## Hoja de ruta

- **Fase 1 (esta versión)**: núcleo contable, población heterogénea, 3 dimensiones, 32 sistemas, Monte Carlo, explorador.
- **Fase 2**: dinero que se oxida, CBDC programable (caducidad, límites), privacidad, regla fiscal; shocks (pandemia, crisis bancaria, burbuja, automatización); sensibilidad global (Sobol).
- **Fase 3**: calibración con la Encuesta Financiera de las Familias, INE y Eurostat; validación 2008–2025.
- **Fase 4**: reglas de emisión como smart contracts en Solidity (testnet) y datos on-chain.

## Referencias principales

Godley y Lavoie (2007), *Monetary Economics* · Caiani et al. (2016), *JEDC* ·
Benes y Kumhof (2012), *The Chicago Plan Revisited*, FMI · McLeay, Radia y
Thomas (2014), *Money creation in the modern economy*, Bank of England ·
Taylor (1993) · Nakamoto (2008).

---

Proyecto educativo y de investigación. No constituye asesoramiento financiero.
