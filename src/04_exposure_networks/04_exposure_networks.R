# ==============================================================================
# SCRIPT: 04_exposure_networks.R
# OBJETIVO: Calcular la exposicion estratificada por prestigio (Prestige
#           Exposure) a cada skill de frontera, ano por ano.
#
# CORRECCION CLAVE #1 (julio 2026): antes este script contaba "adoptantes" a
# nivel de SYLLABUS individual (score>0), lo que estaba saturado (~99%).
# Ahora cuenta adoptantes a nivel de CELDA (unitid x fos) segun el criterio
# de Revealed Comparative Advantage (has_skill_rca de 03b), consistente con
# 03d y con los eventos de adopcion/abandono de 03c.
#
# CORRECCION CLAVE #2 (misma fecha, encontrada al debuggear 05): la primera
# version de este fix filtraba `rca_t` a has_skill_rca==1 ANTES de cruzar con
# las celdas, por lo que panel_exposicion_final SOLO tenia una fila para las
# celdas que YA habian adoptado ese skill ese anio. Las celdas que estaban
# "en riesgo" (sin el skill todavia) quedaban sin ninguna fila de exposicion
# -- es decir, sin dato, no con exposicion=0. Esto rompia el merge en 05
# (100% de NA en exp_elite/exp_base para el risk set de adopcion). Ahora se
# construye explicitamente el cruce COMPLETO celda x skill-de-frontera (para
# TODAS las celdas del sistema, hayan adoptado o no), y se calcula
# exp_elite/exp_base para cada una, restando la auto-adopcion solo cuando
# corresponde.
#
# ALCANCE ACTUAL (nota metodologica honesta, sigue vigente)
# -------------------------------------------
# Esta version calcula una exposicion "global" dentro de cada estrato
# (conteo de adoptantes-celda R1 vs. no-R1 en TODO el sistema, restando la
# auto-adopcion). Esto opera el mecanismo (1) del README -- cascada
# jerarquica / vertical -- pero AUN NO implementa una matriz de adyacencia
# estructural W (mecanismo 2) ni el spillover intra-institucional entre
# campos (mecanismo 3).
#
# Depende de 02 (panel maestro con is_r1), 03b (matriz RCA por celda-skill-
# año) y 03d (seleccion de skills de frontera).
#
# AUTOR: Roberto Cantillan Carrasco
# FECHA: Julio 2026
# ==============================================================================

library(data.table)

setDTthreads(threads = min(4L, parallel::detectCores() - 2L))

dir_interim <- "data/interim"
path_maestro  <- file.path(dir_interim, "panel_maestro_curricular_2000_2017.rds")
path_frontera <- file.path(dir_interim, "metricas_frontera_anual.rds")
dir_rca       <- file.path(dir_interim, "rca_by_year")

output_exposure <- file.path(dir_interim, "panel_exposicion_final.rds")

message("[1/4] Cargando esqueleto institucional y clasificaciones de frontera...")
panel_maestro <- readRDS(path_maestro)
celda_is_r1 <- unique(panel_maestro[, .(unitid, fos, year, is_r1)])

metricas_frontera <- readRDS(path_frontera)
# FIX (julio 2026): usar la lista de skills de frontera FIJADA solo con el
# periodo base (2000-2001), no el flag is_frontier recalculado cada año --
# de lo contrario la cobertura de exposicion para las skills que usan los
# modelos causales cae de 98/100 (2000) a 57/100 (2017), generando
# exposicion faltante (no cero) para años posteriores.
top_skills_fijas <- readRDS("data/interim/top_skills_baseline.rds")

anios_panel <- sort(unique(celda_is_r1$year))
lista_exposicion_anual <- list()

message("[2/4] Calculando exposicion estratificada anio por anio (base RCA)...")

for (ano in anios_panel) {
  path_csv_anual <- file.path(dir_rca, paste0("rca_", ano, ".csv"))
  if (!file.exists(path_csv_anual)) next

  message(paste("-> Procesando red de exposicion para el anio:", ano))

  frontera_t <- data.table(skill = top_skills_fijas)
  if (nrow(frontera_t) == 0) next

  celdas_t <- celda_is_r1[year == ano, .(unitid, fos, is_r1)]

  rca_t <- fread(path_csv_anual, select = c("unitid", "fos", "skill", "has_skill_rca"))
  rca_frontier_t <- rca_t[skill %in% frontera_t$skill]
  rca_frontier_t <- rca_frontier_t[celdas_t, on = .(unitid, fos), nomatch = 0L]  # adjunta is_r1

  # Totales de adoptantes por skill (SOLO donde has_skill_rca==1), R1 vs no-R1
  adopciones_agregadas <- rca_frontier_t[has_skill_rca == 1L, .(
    adopciones_r1_totales  = sum(is_r1 == 1L),
    adopciones_non_totales = sum(is_r1 == 0L)
  ), by = .(skill)]
  # Skills de frontera sin ningun adoptante ese anio: totales en 0
  adopciones_agregadas <- adopciones_agregadas[frontera_t, on = "skill"]
  adopciones_agregadas[is.na(adopciones_r1_totales), adopciones_r1_totales := 0L]
  adopciones_agregadas[is.na(adopciones_non_totales), adopciones_non_totales := 0L]

  # CRUCE COMPLETO: TODAS las celdas del sistema x TODOS los skills de
  # frontera de ese anio (no solo las que ya adoptaron)
  exposicion_t <- celdas_t[, .(skill = frontera_t$skill), by = .(unitid, fos, is_r1)]
  exposicion_t <- rca_frontier_t[, .(unitid, fos, skill, has_skill_rca)][
    exposicion_t, on = .(unitid, fos, skill)]
  exposicion_t[is.na(has_skill_rca), has_skill_rca := 0L]

  exposicion_t <- adopciones_agregadas[exposicion_t, on = "skill"]

  exposicion_t[, `:=`(
    exp_elite = adopciones_r1_totales - fifelse(is_r1 == 1L & has_skill_rca == 1L, 1L, 0L),
    exp_base  = adopciones_non_totales - fifelse(is_r1 == 0L & has_skill_rca == 1L, 1L, 0L)
  )]

  exposicion_t[, year := ano]

  lista_exposicion_anual[[as.character(ano)]] <- exposicion_t[, .(unitid, fos, year, skill, exp_elite, exp_base)]

  rm(rca_t, rca_frontier_t, celdas_t, adopciones_agregadas, exposicion_t)
  gc()
}

message("\n[3/4] Consolidando panel relacional e incorporando rezago temporal (t-1)...")
panel_exposicion <- rbindlist(lista_exposicion_anual)

# La exposicion del anio t-1 afecta la adopcion en el anio t
panel_exposicion[, year_lagged := year + 1L]

message("[4/4] Guardando archivo analitico de exposicion...")
saveRDS(panel_exposicion, file = output_exposure, compress = "gzip")

message(sprintf("Listo. %s filas en panel_exposicion_final.rds", format(nrow(panel_exposicion), big.mark=",")))
message(sprintf("exp_elite: media=%.1f, min=%.1f, max=%.1f",
                mean(panel_exposicion$exp_elite), min(panel_exposicion$exp_elite), max(panel_exposicion$exp_elite)))
message(sprintf("exp_base:  media=%.1f, min=%.1f, max=%.1f",
                mean(panel_exposicion$exp_base), min(panel_exposicion$exp_base), max(panel_exposicion$exp_base)))
