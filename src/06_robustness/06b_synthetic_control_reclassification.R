# ==============================================================================
# SCRIPT: 06b_synthetic_control_reclassification.R
# OBJETIVO: Corregir la amenaza de identificacion detectada en 06 (pre-
#           tendencias significativas en el hazard de abandono, que violan
#           el supuesto de tendencias paralelas de un DiD/event-study
#           estandar). Se usa Generalized Synthetic Control (Xu 2017, paquete
#           gsynth/fect), que construye un contrafactual ponderado para CADA
#           institucion promovida a partir del pool de control, ajustado
#           explicitamente a reproducir su trayectoria PRE-tratamiento -- por
#           construccion, si el ajuste pre-tratamiento es bueno, elimina la
#           pre-tendencia divergente que encontramos en 06.
#
# UNIDAD DE ANALISIS: unitid x year (no celda x skill x year como en 05/06),
# porque el tratamiento (promocion Carnegie) es un atributo institucional, y
# gsynth necesita un panel unidad x tiempo. El outcome es la TASA de
# adopcion/abandono de esa institucion ese anio, agregando sobre todas sus
# celdas (fos) x skills de frontera en riesgo.
#
# Usa la misma cohorte de tratamiento (clean_promotion, 01a) y el mismo
# grupo de control (nunca promovidas limpiamente, excluye siempre-R1) que
# 06_event_study_reclassification.R, para comparabilidad directa.
#
# AUTOR: Roberto Cantillan Carrasco
# FECHA: Julio 2026
# ==============================================================================

library(data.table)
library(gsynth)

setDTthreads(threads = min(4L, parallel::detectCores() - 2L))

dir_interim <- "data/interim"

message("[1/5] Cargando cohortes de tratamiento (identico a 06)...")
carnegie <- fread(file.path(dir_interim, "carnegie_prestige_panel_2000_2017.csv"))
setorder(carnegie, unitid, year)

cohortes_promocion <- carnegie[clean_promotion == TRUE, .(cohort_promocion = min(year)), by = unitid]
siempre_r1 <- carnegie[year == 2000 & prestige_tier_num == 3, unique(unitid)]

trat_unitid <- unique(carnegie[, .(unitid)])
trat_unitid <- cohortes_promocion[trat_unitid, on = "unitid"]
trat_unitid <- trat_unitid[!unitid %in% siempre_r1]
trat_unitid[, cohort_promocion := as.numeric(cohort_promocion)]
trat_unitid[is.na(cohort_promocion), cohort_promocion := Inf]

message(sprintf("  Tratadas: %d | Control: %d", sum(is.finite(trat_unitid$cohort_promocion)),
                 sum(is.infinite(trat_unitid$cohort_promocion))))

message("[2/5] Cargando eventos y agregando a tasa institucion x anio...")
metricas_frontera <- readRDS(file.path(dir_interim, "metricas_frontera_anual.rds"))
top_skills <- readRDS("data/interim/top_skills_baseline.rds")  # FIX: fijado solo con base 2000-2001

eventos <- readRDS(file.path(dir_interim, "adoption_abandonment_events.rds"))
eventos_top <- eventos[skill %in% top_skills & !es_primer_anio_observado]
rm(eventos); gc()

eventos_top <- eventos_top[trat_unitid, on = "unitid", nomatch = 0L]  # excluye siempre-R1

# Agregar a nivel institucion x anio: tasa de adopcion (entre celdas-skill
# en riesgo de adoptar) y tasa de abandono (entre celdas-skill en riesgo de
# abandonar)
panel_adopcion <- eventos_top[has_skill_lag == 0L, .(
  tasa_adopcion = mean(adopta_evento), n_riesgo_adopcion = .N
), by = .(unitid, year, cohort_promocion)]

panel_abandono <- eventos_top[has_skill_lag == 1L, .(
  tasa_abandono = mean(abandona_evento), n_riesgo_abandono = .N
), by = .(unitid, year, cohort_promocion)]

rm(eventos_top); gc()

# Variable de tratamiento binaria (0/1), absorbente
panel_adopcion[, D := as.integer(is.finite(cohort_promocion) & year >= cohort_promocion)]
panel_abandono[, D := as.integer(is.finite(cohort_promocion) & year >= cohort_promocion)]

message(sprintf("  Panel adopcion: %d filas (unidad x anio) | Panel abandono: %d filas",
                 nrow(panel_adopcion), nrow(panel_abandono)))

df_adopcion <- as.data.frame(panel_adopcion[, .(unitid, year, tasa_adopcion, D)])
df_abandono <- as.data.frame(panel_abandono[, .(unitid, year, tasa_abandono, D)])

message("[3/5] Estimando Generalized Synthetic Control -- ADOPCION...")
set.seed(20260701)
gs_adopcion <- gsynth(
  tasa_adopcion ~ D, data = df_adopcion, index = c("unitid", "year"),
  force = "two-way", CV = TRUE, r = c(0, 5), se = TRUE,
  inference = "parametric", nboots = 100, parallel = TRUE, cores = 4
)

message("[4/5] Estimando Generalized Synthetic Control -- ABANDONO...")
set.seed(20260701)
gs_abandono <- gsynth(
  tasa_abandono ~ D, data = df_abandono, index = c("unitid", "year"),
  force = "two-way", CV = TRUE, r = c(0, 5), se = TRUE,
  inference = "parametric", nboots = 100, parallel = TRUE, cores = 4
)

message("\n--- SYNTHETIC CONTROL: ADOPCION ---")
print(gs_adopcion)
cat("\nATT promedio:\n")
print(gs_adopcion$est.avg)

message("\n--- SYNTHETIC CONTROL: ABANDONO ---")
print(gs_abandono)
cat("\nATT promedio:\n")
print(gs_abandono$est.avg)

message("[5/5] Guardando resultados y figuras...")
dir.create("outputs/tables", showWarnings = FALSE, recursive = TRUE)
dir.create("outputs/figures", showWarnings = FALSE, recursive = TRUE)

saveRDS(list(adopcion = gs_adopcion, abandono = gs_abandono),
        file.path(dir_interim, "gsynth_reclasificacion.rds"))

sink("outputs/tables/tabla_synthetic_control_reclasificacion.txt")
cat("=== SYNTHETIC CONTROL: ADOPCION ===\n")
print(gs_adopcion)
cat("\nATT dinamico (por periodo relativo):\n")
print(gs_adopcion$est.att)
cat("\n\n=== SYNTHETIC CONTROL: ABANDONO ===\n")
print(gs_abandono)
cat("\nATT dinamico (por periodo relativo):\n")
print(gs_abandono$est.att)
sink()

pdf("outputs/figures/synthetic_control_reclasificacion.pdf", width = 9, height = 5)
plot(gs_adopcion, main = "Synthetic Control: efecto de la promocion a R1 sobre ADOPCION")
plot(gs_adopcion, type = "counterfactual", raw = "band",
     main = "Synthetic Control: trayectoria real vs. contrafactual -- ADOPCION")
plot(gs_abandono, main = "Synthetic Control: efecto de la promocion a R1 sobre ABANDONO")
plot(gs_abandono, type = "counterfactual", raw = "band",
     main = "Synthetic Control: trayectoria real vs. contrafactual -- ABANDONO")
dev.off()

message("Listo: outputs/tables/tabla_synthetic_control_reclasificacion.txt y outputs/figures/synthetic_control_reclasificacion.pdf")
