# Tasas ajustadas según la dirección institucional

```bash
python3 src/20_adjusted_direction/run_adjusted_direction.py --tag adjusted_direction1
```

Requiere la corrida completa `incorporation_ipeds_origin1` y sus insumos locales.
El mismo comando reanuda los bloques terminados. No modifica la corrida anterior.
La ejecución completa utiliza **2.070 actividades y ambos umbrales**. La opción
`--smoke --tag adjusted_direction2_smoke` sirve sólo para verificar el código
con dos bloques (64 actividades); no respalda conclusiones sustantivas.

## Pregunta y población

¿Persiste una diferencia en las tasas de primera incorporación documentada
entre oportunidades asociadas a emisores superiores, similares e inferiores,
al comparar una misma composición de receptores y ajustar sus características?

Se reconstruye el conjunto de riesgo de la etapa 17 y se excluyen reentradas:
dos años cubiertos bajos, seguidos o no por dos años cubiertos altos, sin
presencia sostenida cubierta anterior. Cobertura mínima: nueve syllabi en
cada uno de los cuatro años. Los años de incorporación son 2008–2016,
con seguimiento hasta 2017. Los cortes reproducen exactamente los anteriores.

El origen es el primer par alto documentado del emisor; ambos extremos usan
selectividad y perfiles institucionales de ese mismo año. Los orígenes
anteriores a 2002 carecen de perfiles y no se rellenan con años posteriores.
La medida institucional es selectividad de admisión, no prestigio directamente
observado. Los scores siguen pendientes de validación contra los syllabi.

## Denominadores y ajuste

Se analizan por separado el canal entre universidades de la misma disciplina
y el canal de disciplinas distintas. Un emisor debe estar alto en t−2 y t−1.
Cada oportunidad receptor×habilidad×año reparte peso total **uno** entre cinco
intervalos del gap S_receptor(origen)−S_emisor(origen), según la fracción de
emisores comparables en cada intervalo. Los intervalos son los de la figura
anterior: extremos mayores a una DE, intermedios de 0,25–1 DE y centro ±0,25 DE.
No se cuentan como cinco incorporaciones ni se atribuyen emisores reales.

Se requiere información comparable para al menos 50% de los emisores activos
en ambos canales, los controles completos, receptores×habilidades repetidos
y estratos disciplina×año, dentro de cada bloque de actividades, con al menos diez oportunidades fraccionarias
en cada intervalo. La depuración de soporte y repetición se itera hasta
estabilizarse. Sin emisores comparables no existe dirección asignable; esas
oportunidades no entran en estas tasas, aunque sí aparecen en el diagnóstico
del conjunto de riesgo. La población puede diferir de la figura descriptiva.
Cada canal conserva exactamente la misma muestra entre sus dos modelos.

Modelo lineal ponderado con indicadores de dirección y efectos fijos de
programa×habilidad, disciplina×habilidad×año y universidad×año:

1. `strict_history`: score previo, su cuadrado, cambio previo y su cuadrado,
   cobertura observada hasta t y tamaños de los conjuntos de emisores.
2. `institutional_adjusted`: agrega exposición interna y externa entre
   disciplinas, presencia de emisores con perfil conocido, diferencias de
   recursos de enseñanza e investigación, coincidencias de clasificación
   Carnegie y control institucional, antigüedad y cobertura de perfiles.

Las diferencias de recursos son las medias por conjuntos de emisores de la
etapa 17; no son controles particulares de cada intervalo. No se usan
contrataciones fechadas ni efectos fijos de emisores individuales: los
emisores todavía constituyen conjuntos posibles. El efecto fijo
disciplina×habilidad×año absorbe la exposición total de la misma disciplina.

Para cada intervalo b, la tasa ajustada es:

`media(Y) + beta_b − sum(proporcion_bin * beta_bin)`.

Esto equivale a promediar predicciones del modelo bajo el mismo historial y
los mismos efectos fijos de todos los receptores elegibles, cambiando sólo
el indicador de dirección. No es una probabilidad de transmisión de una
díada ni una intervención causal. La estandarización del modelo puede exigir
extrapolación en combinaciones de historial y dirección con poco soporte:
el filtro disciplina×año no garantiza solapamiento en todos los controles.
No se recortan tasas fuera de [0,1]; se reportan como diagnóstico del modelo.

La incertidumbre agrupa todas las representaciones de una oportunidad por
universidad. Las tasas incluyen la incertidumbre de la media receptora y de
la composición entre intervalos, además de los coeficientes. El contraste
descendente−ascendente usa su covarianza conjunta. Los bloques disjuntos
se combinan ponderando por oportunidades receptoras; las influencias de
universidades compartidas se suman antes de calcular la varianza. Es una
combinación de modelos por bloque, no una regresión conjunta de las 2.070
actividades. Las comparaciones entre canales y umbrales son exploratorias.

## Archivos de salida

En `outputs/adjusted_direction/<tag>/`:

- `adjusted_direction.png/pdf/svg`: tasas ajustadas por canal y umbral.
- `adjusted_rates.csv`: tasas, intervalos, receptores y universidades.
- `direction_contrasts.csv`: contraste entre los extremos descendente y
  ascendente, con intervalo y p exploratorio, sin corrección por multiplicidad.
- `rates_by_block.csv`: tasas brutas y ajustadas y denominadores por bloque.
- `model_support_by_block.csv`: muestra, entradas, estratos y tasas fuera
  del intervalo de probabilidades.
- `design.json`, `complete.json`: alcance, huellas y comprobación de finalización.

Paneles, pesos e influencias se construyen en
`data/derived/adjusted_direction/<tag>/`, excluido de Git. Los paneles se
eliminan tras cada bloque salvo que se indique `--keep-panels`.

Una diferencia descendente positiva que persista bajo el ajuste respaldaría
una **concentración relativa de incorporaciones asociadas con emisores de
mayor selectividad**. Todavía necesitaríamos validar el contenido, contrastar
explicaciones comunes y documentar conexiones para hablar de transmisión.
