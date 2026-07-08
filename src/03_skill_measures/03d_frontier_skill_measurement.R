# ==============================================================================
# SCRIPT: 03d_frontier_skill_measurement.R
# OBJETIVO: Medir asimetria de estatus (tasa_r1 - tasa_non_r1) por skill-anio
#           e identificar "skills de frontera" (percentil 90 de asimetria).
#
# CORRECCION CLAVE (julio 2026): antes este script (03b_frontier_skill_
# measurement.R) definia "tasa de adopcion" como score>0 a nivel syllabus,
# lo que estaba saturado (~99% tanto en R1 como no-R1 -- ver docs/
# replication_notes/known_fixes_junio_2026.md). Ahora usa `has_skill_rca`
# (Revealed Comparative Advantage >= 1) a nivel de CELDA (unitid x fos),
# calculado en 03b_build_rca_adoption_matrix.R. La tasa promedio de
# has_skill_rca es 45.6% -- una medida que realmente discrimina.
#
# AUTOR: Roberto Cantillan Carrasco
# FECHA: Julio 2026
# ==============================================================================
library(data.table)

setDTthreads(threads = 4)

dir_interim <- "data/interim"
path_maestro <- file.path(dir_interim, "panel_maestro_curricular_2000_2017.rds")
dir_rca      <- file.path(dir_interim, "rca_by_year")

message("[1/3] Cargando esqueleto del panel maestro (celda -> is_r1)...")
panel_maestro <- readRDS(path_maestro)
celda_is_r1 <- unique(panel_maestro[, .(unitid, fos, year, is_r1)])

anios_panel <- sort(unique(celda_is_r1$year))
lista_metricas_anuales <- list()

message("[2/3] Iniciando procesamiento por archivos RCA anuales...")

for (ano in anios_panel) {
  path_csv_anual <- file.path(dir_rca, paste0("rca_", ano, ".csv"))
  if (!file.exists(path_csv_anual)) next

  message(paste("-> Procesando anio:", ano))

  celdas_t <- celda_is_r1[year == ano]
  setkey(celdas_t, unitid, fos)

  rca_t <- fread(path_csv_anual, select = c("unitid", "fos", "skill", "has_skill_rca"))
  setkey(rca_t, unitid, fos)

  rca_panel_t <- rca_t[celdas_t, on = .(unitid, fos), nomatch = 0L, allow.cartesian = TRUE]

  denominador_r1     <- celdas_t[, sum(is_r1 == 1L, na.rm = TRUE)]
  denominador_non_r1 <- celdas_t[, sum(is_r1 == 0L, na.rm = TRUE)]

  if (denominador_r1 == 0 | denominador_non_r1 == 0) next

  metricas_t <- rca_panel_t[, .(
    adopta_r1     = sum(has_skill_rca == 1L & is_r1 == 1L, na.rm = TRUE),
    adopta_non_r1 = sum(has_skill_rca == 1L & is_r1 == 0L, na.rm = TRUE)
  ), by = .(skill)]

  metricas_t[, `:=`(
    year        = ano,
    tasa_r1     = adopta_r1 / denominador_r1,
    tasa_non_r1 = adopta_non_r1 / denominador_non_r1
  )]

  metricas_t[, asimetria_status := tasa_r1 - tasa_non_r1]

  pct_90 <- quantile(metricas_t$asimetria_status, 0.90, na.rm = TRUE)
  metricas_t[, is_frontier := fifelse(asimetria_status >= pct_90, 1L, 0L)]

  message(sprintf("   tasa_r1 promedio: %.1f%% | tasa_non_r1 promedio: %.1f%%",
                   100 * mean(metricas_t$tasa_r1), 100 * mean(metricas_t$tasa_non_r1)))

  lista_metricas_anuales[[as.character(ano)]] <- metricas_t

  rm(celdas_t, rca_t, rca_panel_t, metricas_t)
  gc()
}

message("\n[3/3] Consolidando metricas de frontera finales...")
metricas_frontera_final <- rbindlist(lista_metricas_anuales)

saveRDS(metricas_frontera_final, file = file.path(dir_interim, "metricas_frontera_anual.rds"), compress = "gzip")
message(sprintf("Listo. %s filas skill-anio guardadas en metricas_frontera_anual.rds",
                 format(nrow(metricas_frontera_final), big.mark=",")))
message(sprintf("Asimetria de estatus promedio (todo el panel): %.4f", mean(metricas_frontera_final$asimetria_status)))
