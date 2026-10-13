# Visualización de primeras apariciones sostenidas

```bash
python3 src/19_diffusion_visuals/build_visuals.py --tag cascades1
```

Requiere la corrida completa `incorporation_ipeds_origin1`. Procesa todas las
2.070 habilidades y ambos umbrales. Reanuda bloques completos con el mismo
comando. Datos intermedios en `data/derived/diffusion_visuals/`, excluidos de Git;
figuras y tablas agregadas en `outputs/diffusion_visuals/<tag>/`.

## Qué se observa

Una primera entrada documentada requiere dos años previos bajos y dos años
consecutivos altos, todos con al menos nueve syllabi, y que no exista antes
otro par alto cubierto en ese programa×habilidad. Es una primera aparición
sostenida **documentada**, no prueba primera adopción real. Esto excluye las
reentradas que sí podían entrar en la etapa 17; por tanto, no replica su muestra.
El corte de presencia y los scores son los de la corrida original.

Las etiquetas describen actividades inferidas a partir de los syllabi, no
habilidades verificadas directamente. Una asociación semánticamente extraña
entre actividad y disciplina requiere contrastar los scores con los documentos
originales. Además, un programa puede tener scores altos antes de su origen
documentado, pero con cobertura inferior al mínimo: ese origen no debe
interpretarse como fecha real de innovación curricular.

Emisores potenciales: presencia alta en t−2 y t−1. La selectividad de ambos
extremos se evalúa en el primer año del par alto documentado del emisor.
No se rellenan orígenes anteriores a 2002 con información posterior.
Se requieren perfiles completos de selectividad, recursos, Carnegie y control,
como en el análisis anterior. Receptor con perfil completo en t−1.

## Dos visualizaciones complementarias

`appearance_sequences.png/pdf/svg`: seis habilidades elegidas por número de
primeras entradas, sin seleccionar su gradiente de selectividad. Para cada
habilidad se elige un emisor focal que permite observar más receptores posteriores
temporalmente compatibles (desempate por origen más antiguo e ID). El criterio
no usa magnitud de selectividad ni dirección. Todos los nodos del panel usan
la selectividad del mismo año de origen del emisor focal, congelada durante el
panel. El emisor debe seguir alto en los dos años previos a cada entrada receptora.
Se informa cuántos programas ya tenían el contenido antes del emisor focal:
**ese emisor no es necesariamente la raíz de una cascada**. No se identifican
transmisiones ni progenitores únicos.

`appearance_explorer.html`: versión local interactiva, con selección de habilidad,
umbral y disciplina receptora, información de cada punto y conexiones temporales
posibles opcionales. Se abre en el navegador. Comparte carpeta con
`direction_rates.png`. Los ejemplos no son representativos de todas las habilidades.

`direction_rates.png/pdf/svg`: cinco intervalos del gap continuo
S_receptor(origen)−S_emisor(origen). Negativo=descendente; positivo=ascendente;
±0,25 SD se usa sólo como banda visual horizontal, no como nueva categoría causal.
El modelo previo conserva diferencias continuas.

Cada oportunidad receptor×habilidad×año distribuye peso 1 entre sus emisores
comparables dentro de cada canal externo. Si 30% de ellos están debajo del
receptor, asigna 0,3 de esa oportunidad y 0,3 de su resultado a esa dirección.
De esta manera no multiplica la incorporación por el número de emisores.
Por canal, se requiere que al menos la mitad de los emisores activos tenga
comparación completa. Sin emisores comparables no hay dirección atribuible:
se conserva en `coverage.csv`, pero no entra en las tasas por dirección.

Las tasas azules se estandarizan usando la misma composición de disciplina×año
en los cinco intervalos, con al menos diez oportunidades fraccionarias por
intervalo en cada estrato común. Se informa cobertura de esos estratos. La
incertidumbre agrupa por universidad, usando influencias de la tasa ponderada.
**Esto es descriptivo:** no controla habilidad×año, historial del receptor o
recursos mediante regresión; no identifica un efecto causal ni un flujo real.
Que una tasa descendente sea mayor puede reflejar propensión de receptores,
popularidad de habilidades, composición de emisores o cobertura.

## Outputs y lectura

- `direction_rates.csv`: tasas brutas y estandarizadas, intervalos y soporte.
- `coverage.csv`: primeras entradas y oportunidades con alguna dirección observable.
- `skill_entry_counts.csv`: selección reproducible de habilidades.
- `examples.json`: nodos mostrados, fuente focal, fechas y selección.
- `design.json`, `complete.json`: alcance y definiciones de la corrida.

Un patrón compatible con top-down sería mayor incorporación asociada con
emisores superiores, tras comparar oportunidades equivalentes, y secuencias
con apariciones previas arriba y posteriores abajo. Estas figuras exploran ese
patrón; se deben contrastar con los modelos ajustados y alternativas de cobertura
antes de interpretarlo como difusión descendente. No dibujar todas las
coincidencias temporales como transmisiones observadas.

## Primera corrida completa: `cascades1`

Completadas las 2.070 actividades, 65 bloques por umbral y 12 ejemplos
interactivos. Primeras entradas documentadas: 96.165 en P75 y 63.551 en P90;
esta muestra excluye reentradas y difiere de la etapa 17.

Tasas estandarizadas en los extremos del gap (diferencias mayores a una DE):

| Canal | Umbral | Descendente | Ascendente |
|---|---|---|---|
| Misma disciplina | P75 | 2,03% | 0,90% |
| Misma disciplina | P90 | 1,13% | 0,60% |
| Disciplinas distintas | P75 | 1,51% | 0,77% |
| Disciplinas distintas | P90 | 0,59% | 0,38% |

Los estratos comunes retienen entre 98,49% y 99,78% del peso de las
oportunidades de cada canal. Hay un gradiente descriptivo descendente bajo
ambos umbrales, pero las secuencias individuales son mixtas. Las tasas no
sustituyen la evidencia más débil de asimetría en los modelos ajustados.

La selección automática también expone asociaciones que requieren auditoría
semántica: por ejemplo, “Install doors or windows.” tiene como emisor focal
Periodismo de Oral Roberts University. No se debe presentar esa asociación
como enseñanza comprobada de la actividad sin consultar los syllabi.

## Contrastes continuos de los modelos ya completados

```bash
python3 src/19_diffusion_visuals/plot_model_gradients.py
```

Produce `outputs/diffusion_visuals/model_gradients1/continuous_gradients.png/pdf/svg`.
Usa los modelos exhaustivos de exposición de la etapa 17, que permiten reentradas;
no sustituye las tasas ajustadas de primeras entradas de la etapa 20.
Compara las especificaciones direccional y ajustada por recursos/tipo institucional,
en ambos canales externos y ambos umbrales. No estima abandono ni riesgos logarítmicos.

La curva es un escenario explícito: una fracción h=0,10 del conjunto cubierto son
emisores comparables con igual gap g. Se conserva esa fracción y las restantes
covariables al variar g, tomando g=0 como referencia. El contraste en puntos
porcentuales es 100h[beta_above max(−g,0)+beta_below max(g,0)]. A cada lado
participa sólo un coeficiente; se utilizan sus errores agrupados ya combinados
entre bloques. El intervalo ±1 DE es ilustrativo, no el percentil de soporte
observado. No se transforma el contraste en una probabilidad de transmisión.

El mismo script audita un mapeo por títulos exactos y únicos a la jerarquía O*NET:
2.067 actividades coinciden, tres no. El mapeo local se guarda en
`data/derived/onet_reference/activity_family_mapping.csv`, excluido de Git.
Las cuatro familias son Information Input (356), Mental Processes (456),
Work Output (660) e Interacting With Others (595). Son familias de actividades,
no una dicotomía validada sociocognitivo/sensoriofísico ni la taxonomía de 161.
Las curvas por familia requieren estimación adicional; este script no las inventa.
