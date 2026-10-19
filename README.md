# Monetary Systems Lab

**Web publicada: https://monetary-systems-lab.onrender.com**  
[![tests](https://github.com/JaimeAndresEspinosa/monetary-systems-lab/actions/workflows/tests.yml/badge.svg)](https://github.com/JaimeAndresEspinosa/monetary-systems-lab/actions/workflows/tests.yml)

**Simulador de sistemas monetarios.** Combina seis piezas (regla de emisión, canal
del dinero nuevo, sistema bancario, propiedades del dinero, privacidad y regla
fiscal), que dan **576 sistemas distintos**, y mide qué le pasa a una economía de
miles de hogares, con y sin crisis: inflación, paro, salarios, vivienda, deuda,
evasión fiscal y, sobre todo, **quién gana y quién pierde riqueza**.

- **Motor**: modelo basado en agentes con contabilidad **stock-flujo consistente**
  (ABM-SFC). Cada euro tiene origen y destino, y cada mes se comprueba que los
  balances de todos los sectores cuadran (error máximo ≈ 10⁻¹⁵).
- **Calibrado con datos reales** de España (Eurostat y Cuentas Distribucionales
  de Riqueza del BCE) por el método de los momentos simulados.
- **Sensibilidad global** (índices de Sobol) para separar las conclusiones robustas
  de las que dependen de un supuesto.
- **Smart contracts**: cada regla monetaria está implementada en Solidity, probada en
  una cadena Ethereum local y verificada frente al simulador; la regla de oferta fija
  se calibra con los datos on-chain de Bitcoin.

## Resultados principales

Calibración España, 10 años, mediana de 5 simulaciones por sistema. Pico de paro en la
pandemia: el máximo mensual cuando la crisis llega en el año 3.

| Sistema | Inflación | Paro | Δ cuota 10 % más rico | Deuda pública | Evasión (% PIB) | Paro máx. en pandemia |
|---|---|---|---|---|---|---|
| Actual (BCE) | 2,9 % | 12,9 % | −2,5 pp | 84 % | 0,72 % | 22,4 % |
| Patrón oro | 2,4 % | 11,7 % | −2,5 pp | 71 % | 0,68 % | 23,4 % |
| Bitcoin como moneda (con banca) | 0,6 % | 12,3 % | **+5,1 pp** | 77 % | 0,67 % | 24,7 % |
| Bitcoin libertario (reserva 100 %, anónimo, sin déficit) | **−3,2 %** | **20,8 %** | −0,8 pp | **151 %** | 1,35 % | 29,5 % |
| Chicago Plan (algoritmo 2 %, gasto público, reserva 100 %) | 4,9 % | 10,9 % | −3,4 pp | 52 % | 0,73 % | 19,9 % |
| Euro digital (diseño BCE, rastreable) | 2,6 % | 13,3 % | −0,3 pp | 75 % | **0,14 %** | 22,8 % |
| Dinero que se oxida (Gesell) | 4,3 % | 11,5 % | −1,6 pp | 66 % | 0,76 % | **19,2 %** |
| Algoritmo 2 % + dividendo + euro digital | 3,6 % | 12,2 % | −2,2 pp | 57 % | 0,15 % | 21,2 % |

Lo que sale del barrido completo (efecto principal de cada pieza sobre las 576 combinaciones):

1. **La regla de emisión decide quién se queda la riqueza.** Explica una horquilla de
   5,2 pp en la cuota del 10 % más rico; ninguna otra pieza pasa de 1,4 pp. Con oferta
   fija el dinero escasea, los activos reales (empresas, vivienda) se revalorizan y el
   10 % más rico gana cuota: baja inflación a cambio de más desigualdad.
2. **El dinero muy escaso y sin estabilizadores no aguanta.** El "Bitcoin libertario"
   entra en deflación (−3,2 %) con un paro del 21 %, y la deuda pública sube al 151 %
   aunque haya regla de equilibrio: en deflación los ingresos caen, la deuda pesa más
   en términos reales y las prestaciones siguen pagándose.
3. **En una crisis importa más qué se puede hacer con el dinero que quién lo emite.** En
   la pandemia, la propiedad del dinero mueve el pico de paro en 6 pp; después van la
   regla fiscal (2,2 pp) y el canal (1,9 pp). Que el dinero nuevo entre por gasto
   público amortigua más que si entra por los bancos.
4. **La trazabilidad recauda, pero tiene un coste que el modelo no mide.** Un euro digital
   rastreable reduce la evasión del 0,72 % al 0,14 % del PIB; el coste en privacidad
   y control no se cuantifica en euros (el contrato `ProgrammableCBDC` muestra la
   función `freeze()` que lo hace posible).
5. **Las reglas son programables de verdad.** Ejecutadas como smart contracts durante 10
   años, la oferta fija con halvings y el algoritmo con dividendo coinciden con el
   simulador con una diferencia de 10⁻¹⁶–10⁻¹⁴.

**Validación.** Tras calibrar, la distancia a los datos de España cae de 7,1 a 1,8: paro
13 % (España 15 %), deuda pública 79 % (105 %), 10 % más rico 47 % (54 %), y el modelo
reproduce el signo de la ley de Okun (−0,32 frente a −0,66) y de la curva de Phillips
(−0,67 frente a −0,86). No reproduce bien la cuota del 50 % más pobre ni el nivel de
crédito privado (ver Limitaciones).

## Qué hay en la web

| Sección | Qué hace |
|---|---|
| **Laboratorio** | Elige las seis piezas y una crisis; Monte Carlo con mediana y banda 10–90 %, 28 indicadores, reparto de la riqueza por decil (efecto Cantillon), por dónde entra el dinero nuevo, balances y flujos de todos los sectores |
| **Comparar** | Tres sistemas con la misma economía, las mismas semillas y la misma crisis |
| **Explorador** | Las 576 combinaciones × 5 escenarios (14.400 economías), ordenables y filtrables, con el **efecto principal** de cada pieza |
| **Sensibilidad** | Índices de Sobol S1 y ST de ocho supuestos sobre seis resultados en cuatro sistemas, y qué parte de la varianza es puro azar |
| **Datos reales** | Momentos y hechos estilizados de España frente al modelo, parámetros calibrados y las series originales |
| **Blockchain** | Datos reales de Bitcoin y stablecoins, contratos frente a simulador, coste en gas y el código de los contratos |
| **Metodología** | Agentes, contabilidad, ecuaciones, calibración, tests, limitaciones y referencias (en español y en inglés) |

### Las seis piezas

| Dimensión | Opciones |
|---|---|
| Regla de emisión | discrecional (Taylor + QE) · algoritmo del 2 % · patrón oro · oferta fija con halvings (calibrada con Bitcoin) |
| Canal del dinero nuevo | bancos (compra de bonos) · gasto público · dividendo ciudadano · mineros/validadores |
| Sistema bancario | reserva fraccionaria · reserva del 100 % (Chicago Plan) |
| Propiedades del dinero | normal · se oxida (Gesell) · euro digital programable (límite de 3.000 €, estímulos que caducan) |
| Privacidad | mixta (actual) · anónima · totalmente rastreable |
| Regla fiscal | déficit libre · presupuesto equilibrado |

Crisis: pandemia · crisis bancaria · shock energético · boom de automatización.

## Cómo arrancarla

En Windows, doble clic en **`iniciar.bat`**. O a mano:

```bash
pip install -r requirements.txt
python -m uvicorn app:app --port 8000
```

y abre http://localhost:8000. La web y la API solo necesitan `fastapi`, `uvicorn` y `numpy`.

## Reproducir todos los resultados

```bash
pip install -r requirements-dev.txt          # tests del modelo
pip install --pre -r requirements-chain.txt  # contratos (Solidity + cadena local)

python scripts/fetch_data.py        # Eurostat + BCE  -> data/spain.json
python scripts/calibrate.py         # SMM             -> data/calibration.json
python scripts/fetch_onchain.py     # Bitcoin + stablecoins -> data/onchain.json
python scripts/build_grid.py        # 576 sistemas x 5 escenarios -> data/grid.json
python scripts/build_sensitivity.py # Sobol           -> data/sensitivity.json
python scripts/contracts_demo.py    # contratos vs modelo, gas -> data/contracts_demo.json
python -m pytest                    # ~760 tests
```

Desplegar los contratos en la testnet Sepolia (con tu propia clave de pruebas y
SepoliaETH de un faucet; nunca subas la clave al repositorio):

```bash
python scripts/deploy_contracts.py   # lee RPC_URL y PRIVATE_KEY del entorno
```

## Estructura

| Archivo | Contenido |
|---|---|
| `msl/config.py` | Catálogo de dimensiones, crisis y parámetros (calibrados) |
| `msl/economy.py` | Balances de los 5 sectores, 8 instrumentos y asientos de doble entrada |
| `msl/model.py` | Agentes y comportamiento mes a mes |
| `msl/metrics.py` | Gini, cuotas e indicadores |
| `msl/experiments.py` | Monte Carlo y barrido de combinaciones |
| `msl/sensitivity.py` | Índices de Sobol (Saltelli / Jansen) |
| `msl/validation.py` | Momentos y hechos estilizados frente a los datos reales |
| `msl/chain.py` | Compilación y despliegue de los contratos |
| `contracts/*.sol` | `HalvingToken`, `AlgorithmicDividend`, `DemurrageToken`, `ProgrammableCBDC`, `TokenizedMortgage` |
| `app.py` | API FastAPI |
| `static/` | Web (HTML, CSS y JavaScript sin dependencias; gráficos SVG propios; español e inglés) |
| `data/` | Datos reales descargados y resultados precalculados |
| `tests/` | Contabilidad de las 576 combinaciones y crisis, mecanismos, validación y contratos |

### API

| Endpoint | Devuelve |
|---|---|
| `GET /api/catalog` | Dimensiones, opciones, crisis, indicadores y parámetros |
| `POST /api/simulate` | Monte Carlo de un sistema: series con bandas, resumen, deciles, balances y flujos |
| `GET /api/grid?scenario=none` | Las 576 combinaciones precalculadas en un escenario |
| `GET /api/sensitivity` | Índices de Sobol |
| `GET /api/validation` | Calibración y series de España |
| `GET /api/onchain` | Bitcoin y stablecoins |
| `GET /api/contracts` | Resultados de los contratos y su código |

## Publicarla

Está desplegada en Render con `render.yaml` (plan gratuito: la primera visita tras un rato sin uso tarda ~50 s en despertar). Para otra copia: sube la carpeta a GitHub y en Render crea un *Blueprint* con `render.yaml` (o un
*Web Service* con build `pip install -r requirements.txt` y start
`uvicorn app:app --host 0.0.0.0 --port $PORT`). GitHub Actions ejecuta los tests de
modelo y contratos en cada push.

## Limitaciones

Economía cerrada; empresas y bancos agregados; todas las viviendas valen lo mismo
(por eso el 50 % más pobre conserva más riqueza que en España); el crédito privado
es solo bancario; la productividad crece a ritmo constante; la credibilidad de cada
regla es un supuesto. Los resultados muestran **mecanismos y órdenes de magnitud,
no predicciones**: lo relevante son las diferencias entre sistemas con la misma
economía de partida.

## Referencias principales

Godley y Lavoie (2007), *Monetary Economics* · Caiani et al. (2016), *JEDC* ·
Benes y Kumhof (2012), *The Chicago Plan Revisited*, FMI · McLeay, Radia y Thomas
(2014), *Money creation in the modern economy*, Bank of England · Gesell (1916) ·
Saltelli et al. (2010) · Jansen (1999) · Taylor (1993) · Nakamoto (2008).

---

Proyecto educativo y de investigación. No constituye asesoramiento financiero.
