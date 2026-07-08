# ==============================================================================
# SCRIPT: 03b_build_rca_adoption_matrix.R
# OBJETIVO: Reemplazar el criterio de "adopcion" = score>0 (saturado, ~99%
#           de tasa tanto en R1 como no-R1, ver docs/replication_notes) por
#           un criterio de Revealed Comparative Advantage (RCA), tal como
#           especifica el README original del proyecto.
#
# LA UNIDAD DE ANALISIS es la celda (unitid, fos, year) -- no el
# syllabus individual. Se agrega el score de todos los syllabi de esa celda
# por skill, y se calcula el indice RCA clasico (Balassa / Hidalgo-Hausmann):
#
#   RCA[celda, skill, anio] =
#       ( X[celda,skill] / sum_skill X[celda,skill] )
#     / ( sum_celda X[celda,skill] / sum_celda,skill X[celda,skill] )
#
# donde X[celda,skill] = suma de scores DWA de todos los syllabi de esa
# celda para ese skill, ese anio. RCA >= 1 significa que la celda esta MAS
# especializada en ese skill que el promedio del sistema ese anio (criterio
# estandar en la literatura de complejidad economica). has_skill_rca marca
# esa condicion -- a diferencia de score>0, que es casi universal, RCA>=1 es
# selectivo por construccion (el promedio ponderado de RCA a traves de las
# celdas, para un skill dado, es exactamente 1).
#
# AUTOR: Roberto Cantillan Carrasco
# FECHA: Julio 2026
# ==============================================================================

library(data.table)

setDTthreads(threads = min(4L, parallel::detectCores() - 2L))

dir_interim <- "data/interim"
path_maestro <- file.path(dir_interim, "panel_maestro_curricular_2000_2017.rds")
dir_skills   <- file.path(dir_interim, "skills_by_year")
dir_rca      <- file.path(dir_interim, "rca_by_year")

dir.create(dir_rca, showWarnings = FALSE, recursive = TRUE)

message("[1/2] Cargando esqueleto del panel maestro (id -> celda unitid x fos)...")
panel_maestro <- readRDS(path_maestro)
panel_maestro[, id := as.character(id)]
mapa_id_celda <- unique(panel_maestro[, .(id, unitid, fos, year)])

anios_panel <- sort(unique(mapa_id_celda$year))

message("[2/2] Calculando RCA por celda-skill-anio (procesamiento atomico anual)...")

resumen_anual <- list()

for (ano in anios_panel) {
  path_csv_anual <- file.path(dir_skills, paste0("skills_", ano, ".csv"))
  if (!file.exists(path_csv_anual)) next

  message(paste("-> RCA para el anio:", ano))

  mapa_t <- mapa_id_celda[year == ano, .(id, unitid, fos)]
  setkey(mapa_t, id)

  skills_t <- fread(path_csv_anual, colClasses = c(id = "character", skill = "character", score = "numeric"))
  setkey(skills_t, id)

  # Unir syllabus -> celda y agregar score por (celda, skill)
  syl_celda_t <- skills_t[mapa_t, on = .(id), nomatch = 0L, allow.cartesian = TRUE]
  agregado_t <- syl_celda_t[, .(X = sum(score, na.rm = TRUE)), by = .(unitid, fos, skill)]

  if (nrow(agregado_t) == 0) { rm(mapa_t, skills_t, syl_celda_t, agregado_t); next }

  # Totales para el indice RCA
  agregado_t[, row_total := sum(X), by = .(unitid, fos)]     # total de la celda (todos los skills)
  col_total_t <- agregado_t[, .(col_total = sum(X)), by = skill] # total del skill (todo el sistema)
  agregado_t <- col_total_t[agregado_t, on = "skill"]
  grand_total <- sum(agregado_t$X)

  agregado_t[, rca := (X / row_total) / (col_total / grand_total)]
  agregado_t[, has_skill_rca := fifelse(rca >= 1, 1L, 0L)]
  agregado_t[, year := ano]

  out_t <- agregado_t[, .(unitid, fos, year, skill, X, rca, has_skill_rca)]
  fwrite(out_t, file.path(dir_rca, paste0("rca_", ano, ".csv")))

  resumen_anual[[as.character(ano)]] <- data.table(
    year = ano,
    n_celdas = uniqueN(agregado_t, by = c("unitid", "fos")),
    n_pares_celda_skill = nrow(agregado_t),
    tasa_has_skill = mean(agregado_t$has_skill_rca)
  )

  rm(mapa_t, skills_t, syl_celda_t, agregado_t, col_total_t, out_t)
  gc()
}

resumen <- rbindlist(resumen_anual)
fwrite(resumen, file.path(dir_interim, "rca_resumen_anual.csv"))

message("\n--- RESUMEN RCA POR ANIO ---")
print(resumen)
message(sprintf("\nTasa promedio has_skill_rca==1 (todo el panel): %.1f%%  (vs. ~99%% bajo el criterio score>0 anterior)",
                 100 * mean(resumen$tasa_has_skill)))
message("Listo. Matrices RCA anuales en data/interim/rca_by_year/")
