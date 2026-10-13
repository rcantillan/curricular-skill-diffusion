# Selectividad institucional histórica y exposiciones fechadas

Preparar datos públicos (ya descargados en este workspace):

```bash
python3 src/18_institutional_selectivity/prepare_annual_profile.py
```

`--offline` verifica y utiliza sólo archivos locales. Los archivos de IC/ADM,
HD y finanzas proceden de https://nces.ed.gov/ipeds/datacenter/data/ y quedan
en `data/`, excluido de Git. No se usa Clauset en la aplicación IPEDS.

## Medida independiente del currículo

Para cada año 2002–2015 se usa el midpoint del intervalo intercuartílico de
SAT verbal/reading + matemática o ACT compuesto. Se requieren percentiles
válidos, ordenados y al menos 20% de estudiantes reportando ese test. El
midpoint NO es una media observada ni una mediana. Si ambos tests cumplen,
se elige el reportado por el mayor porcentaje de estudiantes. ACT se calibra
a SAT mediante OLS entre instituciones que reportan ambos en EL MISMO AÑO.
No es una concordancia individual oficial; puede introducir diferencias
regionales y entre poblaciones que toman distintos tests. R² y error leave-one-out
quedan en `test_bridge.csv`. La escala se estandariza sobre instituciones de
cuatro años del directorio anual, antes de vincular con nuestra muestra.

Hay medidas separadas de SAT, ACT y rechazo de solicitudes. Ninguna se mezcla
con recursos en un índice de prestigio. La variable primaria es selectividad,
un proxy que no equivale a reputación académica. No se asigna selectividad cero
a instituciones de admisión abierta o sin puntajes reportados.

Recursos: log1p del gasto total nominal en instrucción y en investigación,
en el mismo año, usando F1A y F2 y prefiriendo archivos revisados cuando existen.
No son gasto por estudiante; las diferencias logarítmicas en el mismo año evitan
comparar dólares nominales de años distintos. Se excluye F3 de la comparación
ajustada porque su investigación y servicio público están combinados. No se
interpreta un dato financiero institucional como específico de una disciplina.

Carnegie: categorías exactas registradas en cada HD histórico (`CCBASIC` o
`CARNEGIE`); compara igualdad de categoría dentro del mismo año. No se ordenan
como estatus ni se reemplazan por clasificaciones de 2025. Control institucional
(pública/privada sin fines de lucro/con fines de lucro) se mantiene separado.

## Año de origen: dos definiciones explícitas

El análisis requiere especificar `--origin-rule`; no decide silenciosamente
qué significa origen.

- `lag`: emisor y receptor usan sus posiciones de t−1, cuando observamos
  presencia sostenida previa del emisor antes de la entrada del receptor en t.
- `first_sustained`: para cada emisor×habilidad se identifica el primer año a
  de DOS perfiles consecutivos altos y cubiertos (a y a+1). Emisor y receptor
  usan sus posiciones de a. Esa posición queda congelada para esa relación,
  incluso si el receptor incorpora la habilidad muchos años después. Sólo
  entran fuentes cuya presencia estaba confirmada antes de t. Primera presencia
  documentada no prueba primera adopción real: puede existir antes del registro.

En ambos casos el gap con signo es S_receptor(a)−S_emisor(a). Las exposiciones
descendentes usan max(−gap,0); las ascendentes usan max(gap,0), multiplicadas
por presencia previa del emisor. Se mantienen dos canales: misma disciplina
entre instituciones y otras disciplinas entre instituciones. La diferencia
institucional interna es exactamente cero: no se inventa estatus distinto
para dos disciplinas de la misma universidad.

No se sustituyen datos faltantes por años posteriores ni por el promedio
2004–2006. La serie disponible comienza en 2002: fuentes con origen documentado
en 2000–2001 conservan su presencia en las exposiciones generales, pero NO
aportan una diferencia de selectividad conocida. `origin_support.csv` informa
esa pérdida. El perfil basal producido por `prepare_profile.py` es una auditoría
alternativa y NO es input del modelo anual.

## Modelos y cobertura

Las exposiciones institucionales se dividen por el total de programas cubiertos
de cada pool, incluidos los que no tienen esa habilidad. Se informa además qué
fracción de emisores activos tiene una comparación completa de origen para
selectividad, recursos, Carnegie y control. La muestra ajustada requiere ≥50%
en cada pool con emisores activos. Pools sin presencia previa siguen siendo
exposición cero; no se confunden con pools de emisores activos sin datos.
El receptor debe tener perfil completo en t−1 para definir esas oportunidades
sin emisores; es una condición de selección, no un reemplazo del gap de origen.

`selectivity_base`, `selectivity_direction` y `selectivity_adjusted` utilizan
la misma muestra y los mismos emisores con comparación completa. Agregan,
sucesivamente, exposición conocida, sus direcciones continuas y diferencias
de recursos/igualdad de categoría institucional. Todos incluyen historial propio,
cobertura, tamaños de pools, antigüedad agregada del contenido y cobertura de
perfiles; efectos fijos receptor×habilidad, disciplina×habilidad×año y universidad×año.
Son asociaciones exploratorias, sin identificación causal ni pronóstico.
El matching completo reduce cobertura incluso en los primeros dos modelos;
`model_support_by_block.csv` muestra esa selección. No extrapolar a universidades
sin selectividad observada ni afirmar que se estudió todo el sistema estadounidense.

## Ejecución

Primera presencia documentada del emisor:

```bash
python3 src/17_sustained_incorporation/run_incorporation.py --tag incorporation_ipeds_origin1 --origin-rule first_sustained
```

Posición en el año inmediatamente anterior a la incorporación:

```bash
python3 src/17_sustained_incorporation/run_incorporation.py --tag incorporation_ipeds_lag1 --origin-rule lag
```

Sensibilidad SAT solamente (cambia la población; revisar soporte):

```bash
python3 src/17_sustained_incorporation/run_incorporation.py --tag incorporation_ipeds_sat_origin1 --origin-rule first_sustained --selectivity-measure sat_selectivity
```

Dos umbrales de presencia, todas las 2.070 actividades y 65 bloques por umbral.
El tag nuevo evita mezclar modelos con la corrida anterior. Repetir exactamente
el comando reanuda los bloques terminados. `--keep-panels` conserva paneles
locales pesados. Outputs en `outputs/sustained_incorporation/<tag>/`.

Revisar `incorporation_summary.csv`, `channel_contrasts.csv`,
`model_support_by_block.csv`, `origin_support.csv`, `followup_selection.csv`
y `skipped_models.csv` si existe. La cobertura del perfil nacional no equivale
al soporte final de eventos y emisores. La próxima etapa de comunidades sigue
pendiente de evidencia relacional adecuada.
