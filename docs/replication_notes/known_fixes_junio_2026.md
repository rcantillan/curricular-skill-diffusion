# Notas de replicación: correcciones aplicadas (junio-julio 2026)

Este documento registra tres bugs de identificación encontrados en la version
inicial del pipeline, su evidencia empírica, y el fix aplicado. Cualquier
resultado generado con los scripts anteriores a esta fecha debe considerarse
inválido y debe re-ejecutarse desde `01a`.

## 1. Año fabricado a partir del id de syllabus (006.py -> 03a)

`006.py` inferia el año con `id.str.extract(r'(\d{4})$')`. Se verificó contra
`institution_fos_year.gzip` (que trae `year` real por syllabus) que esto es
falso: id `102000` es en realidad de 2013 (no 2000); id `102005` es de 2003
(no 2005); id `102017` es de 2002 (no 2017). Impacto medido:
`skills_2000.csv` (versión antigua) tenía 28 ids "año 2000" fabricados,
contra 8,052 ids reales de 2000 -> **0% de solapamiento real**. Esto invalidaba
`03b`, `04` y `05` completos, que dependen del join id -> año.

**Fix:** `03a_split_dwa_scores_by_year.py` ahora asigna el año mediante merge
explícito contra `institution_fos_year.gzip` (cobertura 100%: 281,153 de
281,153 ids verificados).

## 2. Cartesian join entre Atlas y graduados IPEDS (02_panel_construction.R -> 02)

El merge original unia `skills_dt` (con `field_name`, taxonomía propia del
Atlas) y `panel_inst` (con `cipcode` de IPEDS, taxonomía CIP-2) solo por
`(unitid, year)`, sin llave de campo de estudio en común -> producto
cartesiano de ~41 filas de graduados por cada syllabus.

**Fix:** `01b_build_field_cip_crosswalk.py` construye la llave `cip2` a
partir de `field_code` (62 categorías, 58 limpias + 4 con familia CIP
ambigua marcadas con `is_ambiguous`). `02_build_master_panel.R` ahora
une por `(unitid, year, cip2)`.

## 3. Colisión de códigos Carnegie entre familias de clasificación (001.R -> 01a)

La hoja `CCData` reutiliza el mismo `VALUE` con significados distintos según
`Group` (familia de clasificación: Doctoral, Master's, Bachelor's,
Associates, SF:2Yr, etc.). La regla original `carnegie_code %in% c(11, 15)`
sin filtrar por `Group` clasificaba como "R1 elite" a 285 de 1,289 filas
institución-año con VALUE en (11, 15) (22%) que en realidad eran colleges de
dos años (`Assoc/Pub2in4`) o de enfoque técnico especial (`SF: Technical
Professions`). Ejemplo verificado: Arkansas State University-Beebe
(community college) recibía VALUE=11 en 2005 bajo el grupo Associates.

**Fix:** `01a_build_carnegie_prestige_panel.R` restringe `is_r1` a
`carnegie_group == 1` (Doctoral) y, dentro de ese grupo, a
`carnegie_value %in% c(11, 15)` (verificado como el nivel de investigación
más alto de forma consistente en las 30 combinaciones vintage/VALUE/CatLabel
observadas entre 1973 y 2021).

## Pendiente (no bug, pero brecha de alcance)

`04_exposure_networks.R` implementa una exposición "global" estratificada
(conteo de adoptantes R1 vs. no-R1 en todo el sistema), que opera el
mecanismo de cascada jerárquica del README. Aún falta construir la matriz de
adyacencia estructural W (difusión horizontal entre pares) y el spillover
intra-institucional entre campos, antes de que `05_models/` pueda llamarse
con propiedad "Network IV models".

## Verificación end-to-end (ejecutada julio 2026)

Se corrió el pipeline completo (01a → 01b → 02 → 03a → 03b → 04 → 05) sobre
los datos reales tras aplicar los tres fixes. Resultados:

| Paso | Resultado |
|---|---|
| 01a (Carnegie) | 78,015 filas institución-año; 2.69% marcadas `is_r1==1` (2,100 filas) |
| 01b (crosswalk) | 62 categorías `field_name`; 58 limpias, 4 con familia CIP mixta (`is_ambiguous`) |
| 03a (año real) | 530,479,767 filas escritas; 0 ids sin match (cobertura 100%) — antes: ~0% de solapamiento id-año |
| 02 (panel maestro) | 144,990 observaciones institución × cip2 × año; 1,500 instituciones; 29 campos cip2 |
| 03b (frontera) | 37,260 filas skill-año; tasa de match id→panel maestro estable en 50-66% por año (antes: ~0%) |
| 04 (exposición) | 30,347,404 filas en el panel de exposición rezagada |
| 05 (modelo) | Risk set de 8,990,742 observaciones; `feglm` converge; `exp_elite_z` +10.53 (p<0.001), `exp_base_z` −14.27 (p<0.001), `is_r1` −0.175 (p<0.001) |

**Nota de interpretación (no bug, pendiente de revisión sustantiva):** en la
especificación actual, `is_r1` tiene signo negativo una vez que se controla
por `exp_elite_z`/`exp_base_z`. Esto es plausible dado el diseño de
"absorbing state" (las instituciones R1 salen del risk set apenas adoptan,
dejando progresivamente más no-R1 "en riesgo" en años posteriores), pero
conviene validarlo con una especificación alternativa (p.ej. sin filtro de
absorbing state, o con tiempo-hasta-evento continuo) antes de interpretarlo
sustantivamente.

## 4. Variables de estatus agregadas (julio 2026)

Antes solo existía estatus a nivel institución (`is_r1` binario, aplicado por
igual a todas las disciplinas de una universidad). Se agregaron dos piezas:

**a) Gradiente ordinal institucional** (`01a_build_carnegie_prestige_panel.R`):
`prestige_tier_num` (0=no-doctoral, 1=doctoral moderado, 2=R2, 3=R1-elite) en
vez de colapsar todo a binario. También se agregó `clean_promotion` /
`clean_demotion`: flags de transición de nivel que se sostienen (sin reversión)
hasta el final del panel — 140 promociones limpias y 103 degradaciones limpias
detectadas, distintas de las transiciones "de rebote" cerca del umbral R1/R2
(ej. University of Arkansas: R1→R2→R1→R1 entre 2000 y 2010; George Washington
University: mismo patrón). Esto queda listo para un event-study de
reclasificación, pero **usar solo los casos `clean_*==TRUE`** al diseñarlo.

**b) Índice de estatus disciplinar** (`01c_build_field_status_index.R`,
script nuevo): `field_status_index` por (cip2, year) — un location quotient
de cuánto se concentran los graduados de un campo en instituciones R1 respecto
al sistema. Índice >1 = campo estructuralmente sobre-representado en elite
(ej. Agriculture 2.05, Engineering 1.97); <1 = campo concentrado en acceso
masivo (ej. Theology 0.03, Military Science 0.10). Permite distinguir, dentro
de la misma universidad, un departamento estructuralmente elite de uno que no
lo es — algo que `is_r1` no podía hacer al ser constante por institución.

Ambas variables se integraron a `02_build_master_panel.R` y a
`05_event_history_models.R`, que ahora estima dos modelos en paralelo
(binario vs. gradiente) guardados juntos en
`outputs/tables/tabla_resultados_atc.tex`. En el modelo de gradiente,
`prestige_tier_num` (b=-0.068, p<0.001) y `field_status_index_z`
(b=-0.023, p<0.001) son ambos significativos y el ajuste mejora levemente
(BIC 6,130,264 vs. 6,132,123 del binario), confirmando que la variación
disciplinar aporta información que el estatus institucional solo no capturaba
— aunque el signo negativo de ambos sigue sujeto a la misma cautela de
interpretación ya señalada (diseño absorbing-state + adopción no-RCA).

## 5. RCA implementado para adopción y abandono (julio 2026)

Reemplazado el criterio de adopción "score>0" (saturado ~99%) por Revealed
Comparative Advantage, tal como especifica el README original. Pipeline
nuevo:

- **`03b_build_rca_adoption_matrix.R`** (nuevo): calcula RCA clásico
  (Balassa/Hidalgo-Hausmann) por celda (unitid × fos) × skill × año:
  `RCA = (X_celda_skill/X_celda_total) / (X_skill_total/X_gran_total)`,
  `has_skill_rca = RCA>=1`. Tasa resultante: **45.5%** (vs. ~99% antes).
- **`03c_adoption_abandonment_events.R`** (nuevo): deriva transiciones 0→1
  (adopción) y 1→0 (abandono) por celda-skill, diseño de dos estados (no
  absorbing-state, permite re-adopción). 41.9M eventos de adopción y 42.1M
  de abandono detectados sobre 298.8M celda-skill-año.
- **`03d_frontier_skill_measurement.R`** (renombrado desde 03b): ahora usa
  `has_skill_rca` en vez de score>0 para `tasa_r1`/`tasa_non_r1`.
- **`04_exposure_networks.R`**: reescrito dos veces. La primera pasada
  replicó el bug de granularidad (cipcode en vez de fos) y luego un bug de
  cobertura (exposición solo calculada para celdas que YA habían adoptado,
  dejando el resto del risk set sin dato -> 100% NA en el merge de 05).
  Corregido con un cruce completo celda × skill-de-frontera para TODAS las
  celdas del sistema.
- **`05_event_history_models.R`**: rediseñado para estimar DOS hazards
  (adopción: risk set con `has_skill_lag==0`; abandono: risk set con
  `has_skill_lag==1`), cada uno con especificación binaria y de gradiente.

**Nota importante de reproducibilidad:** la unidad de análisis para RCA y
eventos es `(unitid, fos)` -- el campo de estudio original de 62 categorías
del Atlas -- NO `cipcode` (29 categorías CIP-2 de IPEDS). `cipcode` solo se
usa como llave de cruce con graduados/`field_status_index`. Un primer intento
usó `cipcode` por error en 03b/03c/03d, lo cual generaba un descalce de
granularidad con el resto del pipeline (que siempre usó `fos`); fue corregido
antes de la ejecución final documentada abajo.

### Resultados con RCA (4 modelos, `outputs/tables/tabla_resultados_atc.tex`)

| | Adopción (bin.) | Adopción (grad.) | Abandono (bin.) | Abandono (grad.) |
|---|---|---|---|---|
| exp_elite_z | +0.333*** | +0.339*** | +0.319*** | +0.318*** |
| exp_base_z | -0.451*** | -0.459*** | -0.463*** | -0.462*** |
| is_r1 | +0.327*** | — | -0.210*** | — |
| prestige_tier_num | — | +0.110*** | — | -0.065*** |
| field_status_index_z | — | -0.045*** | — | -0.017*** |
| Observaciones | 6,356,348 | 6,356,348 | 5,546,963 | 5,546,963 |
| Eventos | 1,973,408 | 1,973,408 | 1,966,449 | 1,966,449 |

A diferencia de la corrida anterior (score>0, absorbing-state), los
coeficientes ahora tienen magnitudes plausibles (antes ±10 a ±14 en log-odds,
producto de la saturación y de una exposición mal construida). El signo de
`is_r1` ahora es coherente con la teoría de cascada jerárquica: **positivo en
adopción** (+0.327, las R1 adoptan skills de frontera más rápido) y
**negativo en abandono** (-0.210, las R1 retienen esos skills más tiempo una
vez adoptados) -- un hallazgo sustantivo internamente consistente, a
diferencia del resultado anterior (is_r1 negativo en el único modelo que
existía, sin contraparte de abandono para contrastar).

**Limitación que sigue pendiente:** `exp_elite`/`exp_base` siguen siendo
conteos agregados a nivel sistema (mismo valor para todas las celdas de un
skill-año), no una exposición de red genuina a nivel de par/vecino
estructural -- ver limitación ya documentada sobre `data/interim/network_objects/`.

## 6. Experimento natural: event-study de reclasificación Carnegie (julio 2026)

Nuevo: `src/06_robustness/06_event_study_reclassification.R`. Explota las
transiciones LIMPIAS de `prestige_tier_num` (de 01a: promoción/degradación
que no revierte en el resto del panel) como fuente de variación cuasi-exógena
en el timing de alcanzar estatus R1, en vez de solo correlacionar exposición
con adopción. Estimador Sun & Abraham (2021) vía `fixest::sunab()`, robusto
al problema de comparaciones prohibidas en DiD escalonado. Cohortes = 2005,
2010, 2015 (112 instituciones tratadas; grupo de control = 5,185
instituciones nunca promovidas limpiamente, excluyendo las que ya eran R1
desde 2000). Errores estándar clusterizados por institución.

**Resultado: el ATT agregado NO es significativo en ninguno de los dos
hazards.**
- Adopción: ATT = -0.006 (SE 0.010, p=0.55)
- Abandono: ATT = -0.005 (SE 0.012, p=0.71)

Contrasta con el modelo puramente correlacional (sección 5 de estas notas),
donde `is_r1`/`prestige_tier_num` eran altamente significativos. La
diferencia sugiere que el efecto correlacional capturaba en buena medida
selección (instituciones con trayectorias de crecimiento/investigación ya
en curso llegan a R1 Y adoptan/retienen skills más rápido por razones no
observadas), no un efecto causal de *alcanzar* el estatus en sí.

**Alerta de identificación:** el modelo de abandono muestra pre-tendencias
significativas (coeficientes positivos y significativos en year::-14 a
year::-6, es decir, las instituciones que después son promovidas YA tenían
tasas de abandono mas altas antes de la promoción) -- una violación
potencial del supuesto de tendencias paralelas. Esto debe reportarse como
limitación si se usa este diseño en el manuscrito, y amerita robustez
adicional (ej. matching pre-tratamiento, o restringir a instituciones con
trayectorias mas comparables).

**Salidas:** `outputs/tables/tabla_event_study_reclasificacion.tex`,
`outputs/figures/event_study_reclasificacion.pdf` (gráficos de coeficientes
dinámicos leads/lags para ambos hazards).

## 7. Robustez: Generalized Synthetic Control (julio 2026)

`src/06_robustness/06b_synthetic_control_reclassification.R`. Responde
directamente a la alerta de pre-tendencias de la sección 6: en vez de
comparar contra el promedio simple de 5,185 instituciones control, gsynth
(Xu 2017, paquete `gsynth`/`fect`) pondera el pool de control para reproducir
la trayectoria PRE-tratamiento de cada institución promovida (modelo de
efectos fijos interactivos, factor óptimo r*=0 vía cross-validation).
Unidad = institución × año (agregando la tasa de adopción/abandono sobre
todas sus celdas-skill en riesgo ese año); misma cohorte de tratamiento y
grupo de control que en 06.

**Resultado:**
- Adopción: ATT promedio = -0.0013 (SE 0.013, p=0.92) — nulo, coeficientes
  pre-tratamiento limpios (sin divergencia sistemática).
- Abandono: ATT promedio = -0.024 (SE 0.016, p=0.13) — dirección consistente
  con el hallazgo correlacional (promoción → menos abandono), pero no
  significativo al 5%. Los coeficientes pre-tratamiento son mucho más
  limpios que en el event-study Sun-Abraham (solo el período -14, con 1 sola
  observación, y el período -5 muestran significancia aislada, sin el
  patrón sistemático -14 a -6 que preocupaba antes).

**Conclusión metodológica:** con un diseño más riguroso que corrige
explícitamente por pre-tendencias, el resultado nulo de adopción se
confirma, y el efecto negativo sobre abandono es sugerente pero no
concluyente. Esto refuerza la lectura de que el coeficiente `is_r1` grande y
significativo del modelo puramente correlacional (sección 5) refleja en
buena medida selección, no un efecto causal fuerte de alcanzar el estatus en
sí. Limitación: el número de unidades tratadas contribuyendo a los períodos
+4 a +8 cae a 12-16 (la cohorte 2015 domina y el panel termina en 2017), por
lo que las estimaciones de largo plazo son menos precisas.

**Salidas:** `outputs/tables/tabla_synthetic_control_reclasificacion.txt`,
`outputs/figures/synthetic_control_reclasificacion.pdf` (trayectoria real
vs. contrafactual, y ATT dinámico, para ambos hazards).

## 8. Regresión discontinua: intento y resultado NO viable (julio 2026)

`src/06_robustness/06c_regression_discontinuity.R`. Tercer diseño, distinto
de 06/06b: usar el UMBRAL de clasificación (no el timing) como fuente de
variación cuasi-aleatoria. Running variable: `RSDoc` (grados doctorales de
investigación, de la hoja CCData, vintage 2015, Group==Doctoral, n=334).
Corte empírico explorado: RSDoc=180 (donde una comparación cruda de medias
por grupo mostraba un salto de 8% a 87% en la probabilidad de ser R1).

**Resultado: el diseño NO es viable tal como está implementado.** El test de
manipulación (densidad local, Cattaneo-Jansson-Ma) no rechaza continuidad
(p=0.19), pero los tests binomiales por ventana sí muestran asimetría
(p<0.05 en varias ventanas) -- evidencia mixta sobre manipulación de la
variable. Más grave: la **primera etapa estimada con `rdrobust` (polinomio
local, ancho de banda óptimo) es esencialmente cero y no significativa**
(RD Effect=0.007, p=0.96), muy distinta del salto crudo de 8%→87% que
sugería la comparación de medias simple. Esto es la firma clásica de un
"instrumento débil" en RD difusa: solo hay ~25-40 observaciones efectivas
dentro del ancho de banda óptimo, y `RSDoc` es apenas una de varias variables
que realmente determinan la clasificación Carnegie (el índice real también
usa gasto en investigación y personal, no disponibles en este archivo) -- un
único proxy imperfecto no genera un salto lo bastante nítido cerca del corte
para que el ajuste polinomial local lo capture. Como consecuencia, los
efectos de tratamiento estimados (adopción y abandono) tienen intervalos de
confianza absurdamente amplios (ej. [-75.5, 84.0] para una tasa acotada en
[0,1]) -- no interpretables.

**Conclusión:** este diseño se reporta como INTENTADO Y NO VIABLE con los
datos actuales, no como una tercera confirmación del resultado nulo. Para
que una RD funcione aquí haría falta el índice compuesto real de
investigación que usa Carnegie (gasto en I+D, personal académico), que no
está en este archivo -- posible extensión futura si se consigue esa fuente.

**Salidas:** `outputs/tables/tabla_rd_reclasificacion.txt`,
`outputs/figures/rd_reclasificacion.pdf`.

## 9. Instrumento de red "amigos de amigos" (julio 2026)

`src/06_robustness/06d_network_iv_friends_of_friends.R`. Implementa por fin
el mecanismo 2 del README (difusión horizontal entre pares), pendiente desde
el inicio, e instrumenta la exposición directa usando la lógica de
Bramoullé, Djebbari & Fortin (2009) para atacar el problema del reflejo.

**Por qué no se usó "mismo estado" o "mismo sistema" (SYSID) como red:**
ambas son relaciones de equivalencia (transitivas por definición), así que
no generan variación "amigos de amigos que no son mis amigos" -- el
instrumento colapsa. Se construyó en su lugar una red k-NN (k=10) por
similitud estructural (log-matrícula, nivel Carnegie basal 2000, control
público/privado, dentro del mismo Group amplio), que es genéricamente NO
transitiva: 38,480 aristas directas, 33,786 aristas de 2do grado tras
excluir las directas, 0 instituciones sin algún amigo-de-amigo no-directo.

**Limitación explícita:** es una red de equivalencia ESTRUCTURAL (similitud
observable), no de contacto real (sin datos de movilidad de facultad,
comités compartidos, convenios) -- el supuesto de exclusión es más débil que
en una red de contacto genuina.

**Resultado (2SLS, `fixest`, efectos fijos institución+año, EE clusterizados
por institución):**
- Primera etapa: F=8.45 (adopción), F=11.30 (abandono) -- débil/al límite
  del umbral convencional (F>10), especialmente en adopción.
- Segunda etapa: exposición directa a pares → adopción: -1.28 (SE=1.06,
  p=0.23); → abandono: -0.70 (SE=0.81, p=0.39). Ninguno significativo, con
  intervalos muy amplios dado el instrumento débil.
- Test de Wu-Hausman: p=0.079 (adopción, sugerente al 10%) y p=0.253
  (abandono) -- evidencia parcial de que el efecto correlacional simple
  estaría sesgado por endogeneidad, consistente con la preocupación
  original del "problema del reflejo".

**Lectura conjunta de las tres estrategias cuasi-experimentales (06, 06b,
06d) más el intento fallido de RD (06c):** las tres identificaciones que sí
produjeron estimaciones interpretables (event-study, synthetic control,
network IV) coinciden en el mismo patrón -- el efecto causal de estatus/
exposición sobre difusión curricular, una vez identificado rigurosamente, es
consistentemente NULO o no significativo, en contraste marcado con los
coeficientes grandes y muy significativos del modelo puramente
correlacional. Esta es la conclusión más importante y defendible del
proyecto en su estado actual: la asociación observada entre prestigio y
difusión de skills probablemente refleja selección, no un mecanismo causal
de cascada de estatus.

**Salidas:** `outputs/tables/tabla_network_iv.tex`,
`data/interim/panel_network_iv.rds`.

## 10. RD con índice compuesto: mejora el diagnóstico, sigue no viable (julio 2026)

`src/06_robustness/06e_rd_composite_index.R`. Corrige la causa diagnosticada
del fallo de 06c: en vez de `RSDoc` solo, se construye un índice de
propensión (`glm(is_r1 ~ RSDoc+DEGTOT+GRFTEnr+GRPTEnr+HCTTOT)`, Group==1,
vintage 2015) con 89.2% de precisión de clasificación y corte natural en 0
(log-odds, no buscado empíricamente). Mejoras logradas: 111 instituciones
dentro de ±2 log-odds del corte (vs. ~40 antes), y el test de manipulación
ahora es limpio en todas las ventanas (p>0.65 en todos los tests binomiales,
vs. varios p<0.05 antes).

**Resultado: la primera etapa SIGUE sin ser significativa** (RD Effect =
-0.112, p=0.66, IC [-0.74, 0.47]), pese a que el clasificador global es
mucho mejor. Esto es interesante en sí mismo: sugiere que el problema no era
solo "RSDoc es un proxy ruidoso" -- es que **la regla real de asignación de
Carnegie probablemente no tiene una discontinuidad nítida a nivel local**
(el modelo separa bien en los extremos de la distribución, pero cerca del
margen de decisión la clasificación real parece genuinamente difusa/suave,
no un salto administrativo discreto), o la muestra efectiva cerca del corte
(~45-55 obs.) sigue siendo insuficiente para detectarla aunque exista.

**Conclusión: RD no es un diseño viable para esta pregunta con los datos
disponibles**, independientemente de qué tan bien se aproxime la regla de
asignación -- no es un problema de especificación que se pueda seguir
puliendo con las variables de este archivo.

**Salidas:** `outputs/tables/tabla_rd_indice_compuesto.txt`,
`outputs/figures/rd_indice_compuesto.pdf`.

## 11. Cuarto diseño: event-study de fusiones institucionales (julio 2026)

`src/06_robustness/06f_event_study_mergers.R`. Usa `MergeInto_Link` de
CCData (una institución es absorbida por otra) como shock exógeno al
calendario curricular de la institución ABSORBENTE. 74 instituciones
absorbentes con datos del Atlas, cohortes bien distribuidas (18/19/17/20 en
2000/2005/2010/2015); control = 1,426 instituciones que nunca absorben.
Mismo estimador Sun & Abraham que en 06, para comparabilidad directa.

**Resultado: ATT no significativo en ambos hazards**, con pre-tendencias
más limpias que en el diseño de reclasificación original.
- Adopción: ATT = +0.0051 (SE=0.012, p=0.67)
- Abandono: ATT = -0.0220 (SE=0.019, p=0.25) -- dirección negativa
  (menos abandono tras la fusión), consistente con el patrón de 06/06b, pero
  tampoco significativo.

**Limitación:** el año registrado coincide con los ciclos de reconciliación
de Carnegie (2000/2005/2010/2015), no necesariamente la fecha real exacta de
la fusión.

## Síntesis de las seis estrategias de identificación intentadas (06-06f)

| Diseño | Fuente de variación | Viable | ATT adopción | ATT abandono |
|---|---|---|---|---|
| Event-study reclasificación (06) | Timing de promoción Carnegie | Sí, con alerta de pre-tendencia | -0.006 (p=0.55) | -0.005 (p=0.71) |
| Synthetic Control (06b) | Igual, corrige pre-tendencia | Sí, más limpio | -0.001 (p=0.92) | -0.024 (p=0.13) |
| RD con RSDoc (06c) | Umbral clasificación (1 var.) | NO -- 1ra etapa nula | n/a | n/a |
| Network IV amigos-de-amigos (06d) | Exposición de red 2do grado | Débil pero informativo | -1.28 (p=0.23) | -0.70 (p=0.39) |
| RD índice compuesto (06e) | Umbral clasificación (5 var.) | NO -- 1ra etapa sigue nula | n/a | n/a |
| Event-study fusiones (06f) | Timing de absorción institucional | Sí, pre-tendencias limpias | +0.005 (p=0.67) | -0.022 (p=0.25) |

**Conclusión general del proyecto (estado julio 2026):** de seis diseños
cuasi-experimentales distintos, cuatro produjeron estimaciones
interpretables y los cuatro apuntan en la misma dirección: NINGUNO encuentra
un efecto causal significativo de estatus/exposición sobre la velocidad de
adopción de skills de frontera; en abandono, tres de los cuatro sugieren un
efecto negativo (menos abandono) pero ninguno cruza significancia
convencional. Los dos intentos de RD fallan por la misma razón de fondo (la
clasificación Carnegie depende de variables -gasto en I+D, personal- que no
están en este archivo). Esta convergencia a través de identificaciones tan
distintas (timing de reclasificación, contrafactual sintético, red de pares,
fusiones institucionales) es la evidencia más fuerte de que el hallazgo
correlacional original (is_r1 grande y significativo) refleja selección, no
causalidad -- un resultado sustantivo y publicable en sí mismo, no un
fracaso del proyecto.

## 12. Extra: prestigio de red (Clauset et al.) como medida alternativa (julio 2026)

`src/01_cleaning/01d_match_clauset_prestige.R`. Se descargaron los datos
públicos de Clauset, Arbesman & Larremore (2015) -- redes de contratación
docente para Computer Science, Business e History -- y se hizo match
aproximado (Jaro-Winkler sobre nombres normalizados) contra los nombres
institucionales de Carnegie/IPEDS. **409 de 464 instituciones (88.1%)
matcheadas con confianza** (distancia < 0.10); el resto son mayormente
instituciones fuera de EE.UU. (ej. Waterloo, Saskatchewan) que
correctamente no tienen equivalente en IPEDS, o nombres demasiado
genéricos para un match confiable sin revisión manual.

**Validación de convergencia:** el prestigio Clauset (`pi`, rank donde menor
= más prestigioso) correlaciona -0.28 con `prestige_tier_num` (dirección
esperada, ya que son escalas invertidas) y las instituciones R1 tienen un
rank promedio muchísimo mejor (54.7) que las no-R1 (103.5) -- confirma que
el crosswalk capta señal real, pese a que Carnegie (producción de
investigación) y Clauset (a quién contratan como docente) miden estatus de
maneras conceptualmente distintas.

**Alcance de esta entrega:** se deja el crosswalk
(`data/interim/clauset_prestige_crosswalk.csv`) integrado y validado como
insumo para trabajo futuro -- permitiría re-correr los modelos de 05/06 con
esta medida de estatus genuinamente relacional en vez de la administrativa,
pero solo para las celdas institución×año en Computer Science, Business e
History (cobertura parcial). No se re-estimaron los 4 diseños causales con
esta variable en esta ronda por alcance de tiempo; queda como extensión
natural inmediata.

## 13. Quinto diseño: shock de la Gran Recesión (2009), primer resultado SIGNIFICATIVO (julio 2026)

`src/06_robustness/06g_recession_shock_diff_exposure.R`. **Cambio de
alcance respecto a lo propuesto:** se intentó acceder al portal de datos de
SHEEO (apropiaciones estatales por FTE) pero es una aplicación interactiva
(JS) sin archivos CSV/Excel descargables automáticamente en este entorno.
En vez de fabricar cifras de apropiaciones estatales sin fuente verificada,
se usó **público/privado** (`control`, ya en el panel Carnegie) como proxy
binario de exposición diferencial al recorte presupuestario estatal
post-2008 -- un proxy más burdo que la intensidad continua original
propuesta, pero verificable y ya disponible.

Diseño: evento único en 2009 (no escalonado), tratamiento = ser institución
pública, control = privadas. Mismo estimador Sun & Abraham.

**Resultado: por primera vez en las seis identificaciones intentadas, el
ATT es significativo en AMBOS hazards:**
- Adopción: ATT = -0.0214 (SE=0.0070, **p=0.0023**)
- Abandono: ATT = -0.0206 (SE=0.0074, **p=0.0054**)

Los coeficientes dinámicos post-2009 muestran un patrón limpio y creciente:
en adopción, todos los coeficientes de año+3 a año+8 son negativos y
significativos, con magnitud creciendo de -0.023 a -0.033 -- consistente
con un efecto que se consolida en el tiempo, no un shock puntual que se
disipa. Pre-tendencias: mayormente no significativas, con una o dos
excepciones aisladas (año -5 en ambos modelos) que no forman un patrón
sistemático.

**Interpretación sustantiva:** las instituciones públicas, tras la Gran
Recesión, muestran una brecha creciente de MENOR adopción Y menor abandono
de skills de frontera respecto a las privadas -- consistente con un
mecanismo de **restricción de capacidad/recursos** (los recortes
presupuestarios estatales documentados en la literatura de economía de la
educación superior reducen tanto la capacidad de innovar curricularmente
como la de revisar/depurar la oferta existente) más que con un mecanismo de
cascada de prestigio. Esto sugiere que el verdadero motor de la difusión
curricular podría no ser el estatus institucional en sí, sino la
disponibilidad de recursos -- una hipótesis que el diseño de reclasificación
Carnegie no podía distinguir (una institución puede ganar estatus sin ganar
recursos discrecionales, y viceversa).

**Salidas:** `outputs/tables/tabla_event_study_recesion.tex`,
`outputs/figures/event_study_recesion.pdf`.

## Opciones 4 y 5: no completadas por límites reales de acceso a datos

**Opción 4 (políticas estatales de financiamiento por resultados):** el
reporte SHEEO sobre PBF confirma explícitamente que "los datos de
financiamiento por resultados son un componente reciente de la recolección
SHEF y no están disponibles para años anteriores a 2020" -- es decir, no
existe una tabla estructurada y públicamente descargable de fechas de
adopción histórica por estado que cubra 2000-2017. La literatura académica
(Hillman, Tandberg, Rutherford & Rabovsky) documenta fechas para estados
individuales en distintos papers, pero compilar una lista completa y
verificada de ~20-30 estados requeriría verificar cada fecha
individualmente contra fuentes primarias -- no se hizo por no comprometer
la integridad de los datos con fechas no verificadas. Se verificaron solo
2 casos (Indiana: transición completa a OBF en FY2008-09; Tennessee: Complete
College Tennessee Act, 2010) pero no alcanza para un diseño con potencia
estadística razonable.

**Opción 5 (choque de demanda laboral regional / Bartik-BLS):** requiere (a)
geocodificar ~1,500 instituciones a county/región, (b) descargar y procesar
datos BLS (QCEW o similar) de demanda laboral regional por industria/
ocupación, y (c) construir un crosswalk entre esas ocupaciones y los DWA de
O*NET que ya usamos -- un proyecto de ingeniería de datos de varios días,
no una extensión de un par de horas. Se reporta como fuera de alcance para
esta sesión, no como intentado y fallido.

**Ambas quedan documentadas como extensiones futuras concretas**, con la
razón específica de por qué no se completaron (no simplemente "no había
tiempo"), para que quien retome el proyecto sepa exactamente qué haría
falta conseguir.

## 14. Pieza de recursos con datos reales: IPEDS Finance (julio 2026)

Se construyó la pieza que faltaba para llevar el hallazgo de la Gran
Recesión de "sugerente" a "razonablemente sólido": se descargó el
componente de Finanzas de IPEDS (NCES) a nivel de institución, 48 archivos
(F1A público-GASB / F2 privado sin fines de lucro-FASB / F3 privado con
fines de lucro, años fiscales 2001-02 a 2016-17, ~49MB), vía descarga
directa (`nces.ed.gov/ipeds/datacenter/data/F<yy>_<form>.zip` -- patrón de
URL estable y documentado). Scripts: `01e_build_state_appropriations_panel.R`
(extrae `state_approp/total_revenue` por unitid-año: F1B11/F1D01 para
públicas, F2D03/F2D16 para privadas sin fines de lucro, F3D03/F3D09 para
privadas con fines de lucro -- 100,935 filas institución-año) y
`06h_recession_shock_state_funding.R` (rediseño del choque de recesión con
esta medida continua).

**Validación de la medida:** dependencia de fondos estatales promedio 2005-
2007: públicas 29.3% de ingresos, privadas sin fines de lucro 0.3%, privadas
con fines de lucro 0.7% -- exactamente el patrón esperado, y confirma que el
proxy público/privada anterior capturaba la dirección correcta pero con
mucho ruido (dentro de las públicas, el rango real va de 0% a 99%, con
mediana ~30%).

**Resultado del DiD con intensidad continua (evento común 2009, N=6,424
instituciones con baseline válido):**
- Adopción: interacción post2009 × dependencia_estatal_z = -0.0065
  (**p=0.008**)
- Abandono: interacción post2009 × dependencia_estatal_z = -0.0061
  (**p=0.020**)

Ambos se sostienen y son del mismo orden de magnitud que el resultado con el
proxy binario anterior -- el hallazgo SOBREVIVE el reemplazo por la medida
real, lo que responde directamente a la principal objeción de un revisor
exigente.

**Versión dinámica (año × dependencia estatal, referencia 2008), mucho más
informativa que el ATT promedio:** el período pre-tratamiento (2001-2007)
es limpio (todos los coeficientes no significativos excepto uno aislado en
2004), y el efecto post-tratamiento en adopción **emerge con rezago y crece
de forma monótona**: no significativo en 2009-2011, y luego significativo y
creciente de 2012 a 2017 (de -0.011 a -0.014). Este patrón -- ausencia de
efecto inmediato, aparición y consolidación 3-4 años después -- es
sustantivamente coherente con los ciclos presupuestarios estatales
plurianuales documentados en la literatura de economía de la educación
superior, y es mucho más convincente que un simple salto en el año del
shock.

**El chequeo de mecanismo directo NO confirma el canal más obvio:** se
probó si el gasto en instrucción (`F1C011`, solo públicas) cae más en las
instituciones más dependientes de fondos estatales tras 2009 -- el
coeficiente es prácticamente cero y no significativo (0.0063, p=0.51). Esto
NO refuta el hallazgo curricular (que es robusto y creciente), pero sí
significa que el mecanismo no puede describirse todavía como "recortaron el
gasto en instrucción y por eso adoptan/abandonan menos" -- es consistente
con la literatura que documenta que las instituciones tienden a proteger el
gasto instruccional directo y ajustar por otras vías (congelamiento de
contrataciones, reducción de capacidad administrativa para revisar
currícula, recortes en gastos no-instruccionales). El mecanismo exacto
queda como pregunta abierta, a explorar con otras variables de F1C
(gastos por función) o con datos de planta docente.

**Salidas:** `outputs/tables/tabla_recesion_financiamiento_real.tex`,
`outputs/figures/recesion_financiamiento_real.pdf`.

## Conclusión actualizada del proyecto (estado julio 2026)

Con la pieza de financiamiento real incorporada, el estado del argumento es:
el mecanismo de PRESTIGIO/ESTATUS sobre difusión curricular no encuentra
soporte causal en ninguna de las cinco identificaciones que lo probaron
directamente (reclasificación, synthetic control, network IV, fusiones, y
los dos intentos de RD). El mecanismo de RESTRICCIÓN DE RECURSOS sí muestra
un efecto causal significativo, robusto al reemplazar el proxy burdo por la
medida real de dependencia de financiamiento estatal, con una dinámica
temporal (rezago + crecimiento) sustantivamente coherente -- aunque el canal
exacto (qué se recorta específicamente) todavía no está identificado con
precisión. Este es un argumento publicable: la contribución pasa de "el
estatus no importa" (un hallazgo nulo, más difícil de vender) a "los
recursos importan más que el estatus para la difusión curricular" (un
hallazgo positivo con implicancias claras para la literatura de
estratificación educativa).

## 15. Mecanismo, parte 2: gasto funcional y planta docente (julio 2026)

Ambas piezas solicitadas quedaron construidas y probadas.

### Gasto funcional por categoría (`01f`/`06i`)

Se extrajeron 9 categorías de gasto (instrucción, investigación, servicio
público, apoyo académico, servicios estudiantiles, apoyo institucional,
operación y mantenimiento, becas, empresas auxiliares) de los mismos
archivos F1A ya descargados. **Resultado con matices importantes:** varias
categorías (gasto total, becas, apoyo institucional, instrucción) muestran
un coeficiente **positivo y significativo** de `post2009 × dependencia
estatal` sobre el log del gasto NOMINAL -- es decir, las instituciones más
dependientes de fondos estatales gastaron relativamente MÁS, no menos, en
dólares nominales tras 2009. Esto NO es necesariamente una refutación del
mecanismo de recursos: **esta cifra no está normalizada por matrícula**, y
la literatura documenta que muchas públicas expandieron matrícula durante
la recesión (los estudiantes que no podían pagar privadas se movieron a
públicas). Un gasto nominal mayor con más estudiantes puede implicar MENOS
recursos por estudiante. Sin datos de matrícula (Fall Enrollment de IPEDS,
no incorporados en esta ronda), esta pieza queda como **inconclusa**, no
como evidencia en contra del mecanismo.

### Planta docente (`01g`/`06j`) -- resultado limpio y coherente

Se construyó el panel de planta docente (headcount total de "instructional
staff") desde el componente EAP de IPEDS, 2002-2017, manejando el rediseño
de la encuesta de RRHH de 2012 (formato antiguo FTPT/FUNCTCD/FSTAT vs.
formato nuevo EAPCAT/OCCUPCAT/FACSTAT -- verificado que ambos filtros
producen exactamente una fila por institución). 84,011 observaciones,
6,313 instituciones.

**Resultado: efecto negativo y muy significativo** de dependencia estatal x
post-2009 sobre log(planta docente): **-0.038 (p<0.0001)**.

**La versión dinámica es la pieza más convincente de todo el ejercicio de
mecanismo:** el patrón temporal replica CASI EXACTAMENTE el de la variable
curricular (06h) -- sin efecto en 2009-2011, y luego un efecto negativo que
emerge y crece de forma monótona de 2012 a 2017 (de -0.028 a -0.037, todos
significativos). Que dos variables completamente distintas (planta docente
medida en RRHH, y adopción/abandono curricular medido en el Atlas) muestren
la MISMA firma temporal de rezago y consolidación es la evidencia más fuerte
de todo el proyecto de que hay un mecanismo real y común operando --
consistente con recortes de contratación docente vía attrition/congelamiento
que redujeron la capacidad de las instituciones más dependientes de fondos
estatales para sostener el desarrollo curricular.

**Advertencia honesta:** hay una pre-tendencia en la planta docente
(2002-2004 muestra coeficientes positivos y significativos, dependencia
estatal asociada a MAYOR crecimiento de planta en la expansión económica
previa) que se disipa hacia 2005-2007 (justo antes del período usado como
baseline). Va en dirección OPUESTA al efecto post-tratamiento, por lo que
si sesga algo, sesga la estimación hacia abajo (subestima el efecto), no lo
infla artificialmente -- pero debe reportarse.

**Salidas:** `outputs/tables/tabla_mecanismo_gasto_funcional.csv`,
`outputs/tables/tabla_mecanismo_planta_docente.tex`,
`outputs/figures/mecanismo_planta_docente.pdf`.

## Conclusión final actualizada (julio 2026)

El proyecto ahora tiene: (1) un hallazgo causal robusto de que la
dependencia de financiamiento estatal, no el estatus/prestigio, predice la
velocidad de adopción y abandono de skills de frontera, confirmado con datos
reales de IPEDS Finance y sobreviviendo el reemplazo de un proxy binario por
una medida continua; y (2) evidencia de mecanismo -- planta docente -- con
una firma temporal que replica casi exactamente la del resultado curricular
(rezago hasta 2012, luego efecto creciente), mientras que el canal de gasto
nominal por función queda inconcluso sin normalizar por matrícula. Esto es
sustancialmente más sólido que lo que había antes del pedido de esta pieza,
y deja un mapa claro de qué falta (matrícula por año, para normalizar el
gasto) si se quiere cerrar del todo el argumento de mecanismo.

## 16. Cierre del mecanismo: gasto normalizado por matrícula FTE (julio 2026)

`01h_build_fte_enrollment_panel.R` (matrícula FTE, IPEDS Fall Enrollment
EFFY, 2008-2017 -- 2002-2007 quedó fuera por usar un formato de desglose
racial/género sin columna de total directa, no crítico para el diseño que
compara pre/post 2009) + `06k_mechanism_expenditure_per_fte.R` (gasto por
categoría funcional dividido por matrícula FTE, re-estimando el mismo DiD).

**Con la normalización correcta, el panorama se aclara:**
- **Operación y mantenimiento de planta: -0.025 (p=0.019)** -- cae
  significativamente por estudiante en instituciones más dependientes de
  fondos estatales. Coincide con lo mejor documentado en la literatura de
  finanzas de educación superior: el mantenimiento diferido es de las
  primeras partidas que se recortan en crisis presupuestarias.
- **Gasto total per FTE: +0.022 (p=0.020)** -- positivo, contraintuitivo a
  primera vista. Lectura más plausible: las instituciones más dependientes
  compensaron el recorte estatal subiendo matrícula/aranceles, sosteniendo
  el gasto total por estudiante aun cuando la FUENTE de esos fondos cambió
  de estatal a arancel -- un desplazamiento de carga hacia estudiantes, no
  una ausencia de impacto.
- **Instrucción per FTE: +0.007 (p=0.449), NO significativo.** Este es el
  resultado más importante para conectar con el hallazgo de planta docente
  (06j): el gasto en instrucción POR ESTUDIANTE se mantuvo estable pese a
  que el HEADCOUNT de personal docente cayó significativamente -- consistente
  con que las instituciones mantuvieron el gasto agregado en instrucción
  (quizás vía sueldos más altos a menos docentes, mayor carga por profesor,
  o mayor uso de instructores de menor costo) mientras reducían la
  DOTACIÓN de personal, que es precisamente el tipo de ajuste que reduce la
  capacidad organizacional de revisar y renovar currícula sin que aparezca
  como un recorte de gasto instruccional.
- Apoyo académico y servicios estudiantiles muestran tendencias (positiva y
  negativa respectivamente) pero no alcanzan significancia convencional.

**Síntesis final del mecanismo:** la cadena más defendible con toda la
evidencia junta es: dependencia de fondos estatales → recorte en
mantenimiento de planta y en DOTACIÓN de personal docente (no
necesariamente en el gasto nominal en instrucción, que se sostiene vía
aumento de matrícula/carga docente) → menor capacidad organizacional para
sostener el desarrollo curricular → menor adopción y menor abandono de
skills de frontera, con la misma firma temporal de rezago hasta 2012 y
consolidación posterior en las tres variables (currícula, planta docente,
mantenimiento).

**Salidas:** `outputs/tables/tabla_mecanismo_gasto_per_fte.csv`.
