# ==============================================================================
# SCRIPT: 03c_adoption_abandonment_events.R
# OBJETIVO: A partir de la matriz RCA (03b, has_skill_rca por celda-skill-año),
#           derivar los eventos de ADOPCION (0->1) y ABANDONO (1->0) por
#           celda (unitid, fos) x skill x año, tal como especifica el
#           README original del proyecto ("skill adoption and skill
#           abandonment events derived from RCA thresholds").
#
# DISEÑO DE DOS ESTADOS (no absorbing-state):
#   - Mientras has_skill_rca==0, la celda esta "en riesgo de adoptar":
#     adopta_evento=1 el primer año que has_skill_rca pasa a 1.
#   - Mientras has_skill_rca==1, la celda esta "en riesgo de abandonar":
#     abandona_evento=1 el primer año que has_skill_rca vuelve a 0.
#   A diferencia del diseño anterior (absorbing state, cumsum<=1), aquí SI
#   se permite re-adopcion despues de un abandono (spells multiples), porque
#   sustantivamente un programa puede recuperar un skill que dejo de dictar.
#
# AUTOR: Roberto Cantillan Carrasco
# FECHA: Julio 2026
# ==============================================================================

library(data.table)

setDTthreads(threads = min(4L, parallel::detectCores() - 2L))

dir_interim <- "data/interim"
dir_rca     <- file.path(dir_interim, "rca_by_year")

message("[1/3] Cargando matrices RCA anuales...")
archivos_rca <- list.files(dir_rca, pattern = "^rca_\\d{4}\\.csv$", full.names = TRUE)
rca_full <- rbindlist(lapply(archivos_rca, fread,
                              select = c("unitid", "fos", "year", "skill", "has_skill_rca")))

message(sprintf("Filas totales RCA cargadas: %s", format(nrow(rca_full), big.mark = ",")))

message("[2/3] Ordenando y detectando transiciones por celda-skill...")
setorderv(rca_full, c("unitid", "fos", "skill", "year"))

rca_full[, `:=`(
  has_skill_previous_observed = shift(has_skill_rca),
  previous_observed_year = shift(year)
), by = .(unitid, fos, skill)]
rca_full[, year_gap := year - previous_observed_year]
# An annual event requires observations in consecutive calendar years.
# Preserve the previous available state for separate interval sensitivities.
rca_full[, has_skill_lag := fifelse(year_gap == 1L,
                                  has_skill_previous_observed, NA_integer_)]

# First observations and observations following a gap restart the annual spell.
rca_full[, adopta_evento  := fifelse(!is.na(has_skill_lag) & has_skill_lag == 0L & has_skill_rca == 1L, 1L, 0L)]
rca_full[, abandona_evento := fifelse(!is.na(has_skill_lag) & has_skill_lag == 1L & has_skill_rca == 0L, 1L, 0L)]
rca_full[, es_primer_anio_observado := is.na(has_skill_lag)]

message("[3/3] Guardando panel de eventos...")
output_path <- file.path(dir_interim, "adoption_abandonment_events.rds")
saveRDS(rca_full, output_path, compress = "gzip")

message("\n--- RESUMEN ---")
message(sprintf("Filas (celda x skill x año): %s", format(nrow(rca_full), big.mark = ",")))
message(sprintf("Eventos de ADOPCION detectados: %s", format(sum(rca_full$adopta_evento), big.mark = ",")))
message(sprintf("Eventos de ABANDONO detectados: %s", format(sum(rca_full$abandona_evento), big.mark = ",")))
message(sprintf("Celda-skill en riesgo de adopcion (has_skill_rca==0, no primer año): %s",
                format(rca_full[has_skill_rca == 0L & !es_primer_anio_observado, .N], big.mark = ",")))
message(sprintf("Celda-skill en riesgo de abandono (has_skill_rca==1, no primer año): %s",
                format(rca_full[has_skill_rca == 1L & !es_primer_anio_observado, .N], big.mark = ",")))
message(sprintf("Listo: %s", output_path))
