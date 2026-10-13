# Incorporación sostenida y relaciones potenciales

Ejecutar desde la raíz del repositorio:

```bash
python3 src/18_institutional_selectivity/prepare_annual_profile.py
python3 src/17_sustained_incorporation/run_incorporation.py --tag incorporation_ipeds_origin1 --origin-rule first_sustained
```

Todas las 2.070 actividades, dos umbrales exploratorios, 65 bloques por umbral.
El origen también puede ser t−1 con `--origin-rule lag` y otro tag. Ver
[medida institucional, temporalidad y cobertura](../18_institutional_selectivity/README.md).
Reanuda bloques terminados al repetir el comando. Un cambio de código o inputs
requiere otro tag. La prueba corta agrega `--smoke` y un tag terminado en `_smoke`.

## Definición temporal

Unidad: receptor (universidad × disciplina) × actividad × año. Años de entrada
2008–2016; 2017 se usa como seguimiento. Todos los cuatro perfiles t−2, t−1,
t, t+1 deben tener al menos nueve syllabi. La selección por seguimiento se
reporta y puede sesgar la población estudiada.

Se fija un corte por actividad usando los percentiles 75 y 90 de los perfiles
2002–2007 con cobertura suficiente. Scores en unidades de desviación estándar
del mismo período. En riesgo: score ≤ corte−0,1 durante t−2 y t−1. Entrada:
score ≥ corte+0,1 durante t y t+1. Los demás casos evaluables son cero. Esto
incluye intensificación de relevancia; no prueba ausencia literal previa ni
primera adopción histórica. Se permiten entradas recurrentes tras una pérdida.
Los umbrales NO están calibrados contra incertidumbre de medición. No hay RCA.
`--margin 0.2 --tag incorporation_margin02` permite otra sensibilidad.

Emisores potenciales: programas con score ≥ corte+0,1 tanto en t−2 como t−1,
ambos con cobertura ≥9. Exposición = proporción de programas previamente
cubiertos que satisfacen esa presencia; incluye ceros y receptores que incorporan
sin emisores observados. Tres pools mutuamente excluyentes: otras disciplinas
de la misma universidad; misma disciplina de otras universidades; otras
disciplinas de otras universidades. Se excluye siempre el propio receptor.
No se multiplican los eventos por el número de emisores. No se exportan vínculos
como si fueran transmisiones identificadas.

Contenido característico: media basal de una disciplina (primero promedio por
programa, después por disciplina) supera en ≥0,25 SD la media de las otras
disciplinas, con igual peso por disciplina. Las exposiciones `*_distinct`
cuentan emisores con contenido característico de su campo que no es también
característico del campo receptor; denominador = mismo pool cubierto. Ese corte
también es exploratorio. No es integración dentro de un curso.

## Estimación y estatus

Modelos lineales de probabilidad. `channels` compara los tres pools con efectos
fijos receptor×actividad, actividad×año, disciplina×año y universidad×año.
Los otros modelos usan receptor×actividad, disciplina×actividad×año y universidad×año.
La proporción de emisores de la misma disciplina es constante dentro de
disciplina×actividad×año para receptores en riesgo (su presencia previa es cero):
se absorbe en esos modelos estrictos y se omite deliberadamente. Por tanto,
su coeficiente en `channels` NO sobrevive a ese control más exigente y puede
representar una tendencia propia del campo y contenido.
Los modelos controlan nivel previo, cambio previo,
sus cuadrados, cobertura previa/actual y tamaños de los tres pools de fuentes.
Sólo pares con dos o más oportunidades elegibles entran al modelo; el soporte
antes y después de esa restricción se guarda en cada `model_support.csv`.
Las tres especificaciones principales usan la misma muestra con los tres pools
de fuentes observables; el modelo de estatus usa un subconjunto adicional.
Cobertura futura determina observabilidad; no entra como predictor.
Estimaciones por bloques disjuntos promediadas por número de filas; la varianza
combina influencias de las mismas universidades entre bloques. No es un único
modelo conjunto y sus efectos pueden depender del bloque de controles comunes.
Si falta algún canal/bloque, el resumen es parcial: revisar `skipped_models.csv`
y `blocks` en el resumen antes de interpretar.

La aplicación actual usa selectividad anual de IPEDS para comparar campos
distintos, sin depender de rankings de contratación. Ambos programas se evalúan
en el año de origen especificado. Los tres modelos de selectividad comparan
dirección y capacidad institucional en una muestra común; véase la documentación
de la etapa 18. Los recursos y Carnegie son características separadas.

La opción histórica `--status-source clauset` reproduce la sensibilidad previa:
estatus sólo para Business, Computer Science e History y años ≥2014, con los
rankings existentes disponibles desde 2013. `status_above` promedia presencia
del emisor × max(estatus_emisor−estatus_receptor,0) sobre fuentes comparables;
`status_below` usa max(estatus_receptor−estatus_emisor,0). Ambos son continuos,
separan direcciones y se calculan exclusivamente dentro de la misma disciplina.
No comparan estatus entre campos. Un efecto positivo de `status_above` sería
compatible con un canal descendente, no una demostración de su mecanismo.
Puede faltar soporte para este modelo: se informa sin invalidar los otros.

No se incorporan geografía ni contratación como si fueran contactos fechados:
los stocks existentes no documentan vínculos anteriores a cada evento. No hay
pronóstico fuera de muestra ni identificación causal en esta etapa. Los shocks
universidad×actividad×año siguen siendo una explicación alternativa importante
de las exposiciones internas. Una asociación no autoriza construir aristas
causales ni comunidades de difusión confirmada.

## Outputs

En `outputs/sustained_incorporation/<tag>/`:

- `incorporation_summary.csv`: asociaciones e intervalos, por umbral y modelo.
  `probability_points_per_10pp` expresa puntos porcentuales de probabilidad por
  diez puntos porcentuales de exposición; no corresponde a los términos de estatus.
- `entry_rates.csv`: oportunidades, entradas y tasas por disciplina y año.
- `channel_contrasts.csv`: diferencias formales entre coeficientes, usando su
  covarianza compartida; no comparar sólo si sus p-valores son distintos.
- `model_support_by_block.csv`: soporte de las muestras efectivamente estimadas.
- `origin_support.csv`: años de origen y disponibilidad de perfiles institucionales
  de los emisores, en la aplicación IPEDS.
- `program_entry_rates.csv`: tasas por universidad×disciplina×año. Son cambios
  observados, no flujos atribuidos a emisores.
- `followup_selection.csv`: proporción de oportunidades con seguimiento.
- `skipped_models.csv`: modelos/canales que no pudieron estimarse, si existen.
- `design.json`, `complete.json`: inputs, definiciones y alcance de la corrida.
- En cada bloque: cortes, distintividad basal, soporte y diagnósticos del modelo.

Los paneles pesados se eliminan después de estimar, salvo `--keep-panels`; los
datos y paneles conservados siguen excluidos de Git. Las comunidades son una
etapa posterior, construida con evidencia relacional y evaluada en otra ventana.
