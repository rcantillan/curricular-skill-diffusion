# ==============================================================================
# SCRIPT: 06c_regression_discontinuity.R
# OBJETIVO: Tercer diseño cuasi-experimental (distinto de 06 y 06b): en vez de
#           usar el TIMING de la reclasificacion (tendencias paralelas), usar
#           el UMBRAL de clasificacion como fuente de variacion cuasi-
#           aleatoria. Instituciones justo arriba/abajo del corte que separa
#           R1 de R2/R3 son "como si" asignadas al azar en ese margen -- una
#           identificacion que NO depende de tendencias paralelas.
#
# RUNNING VARIABLE: RSDoc (grados doctorales de investigacion otorgados),
# tomado directamente de la hoja CCData (no esta en el panel interim, que
# solo guarda VALUE/CatLabel). Restringido a Group==1 (Doctoral), vintage
# 2015 (la cohorte de reclasificacion mas grande, 86 promociones limpias).
#
# LA CLASIFICACION REAL NO ES UN CORTE PURO EN RSDoc (Carnegie usa un indice
# compuesto que tambien incluye gasto en investigacion, personal, etc., no
# disponible en este archivo) -- por eso este es un diseño de RD DIFUSA
# (fuzzy RD): RSDoc predice fuertemente pero no determina por completo
# is_r1. Se verifico empiricamente el salto en la probabilidad de ser R1
# alrededor de RSDoc=180 (8% -> 87%). Se usa `rdrobust` (Calonico-Cattaneo-
# Titiunik) para la estimacion local-polinomial con ancho de banda optimo,
# y `rddensity` para el test de manipulacion de McCrary.
#
# OUTCOME: tasa de adopcion/abandono promedio de la institucion en 2015-2017
# (los datos de skills terminan en 2017, por lo que la ventana post-corte es
# corta -- limitacion explicita).
#
# AUTOR: Roberto Cantillan Carrasco
# FECHA: Julio 2026
# ==============================================================================

library(data.table)
library(readxl)
library(rdrobust)
library(rddensity)

dir_interim <- "data/interim"

message("[1/6] Cargando RSDoc (running variable) para Group==Doctoral, vintage 2015...")
carnegie_raw <- as.data.table(read_excel(
  "data/raw/Longitudinal-Public-Data-File-1973-2021.xlsx", sheet = "CCData"))
doc2015 <- carnegie_raw[YEAR == 2015 & Group == 1, .(
  unitid = as.integer(C_UNITID), RSDoc = as.numeric(RSDoc), VALUE = as.integer(VALUE)
)]
doc2015 <- unique(doc2015[!is.na(unitid) & !is.na(RSDoc)], by = "unitid")
doc2015[, is_r1 := as.integer(VALUE == 15)]

message(sprintf("  Instituciones doctorales 2015 con RSDoc valido: %d", nrow(doc2015)))

message("[2/6] Test de manipulacion de la running variable (McCrary/Cattaneo-Jansson-Ma)...")
cutoff <- 180
dens_test <- rddensity(doc2015$RSDoc, c = cutoff)
print(summary(dens_test))

message("[3/6] Reconstruyendo panel institucion x anio de tasas de adopcion/abandono...")
metricas_frontera <- readRDS(file.path(dir_interim, "metricas_frontera_anual.rds"))
top_skills <- readRDS("data/interim/top_skills_baseline.rds")  # FIX: fijado solo con base 2000-2001

eventos <- readRDS(file.path(dir_interim, "adoption_abandonment_events.rds"))
eventos_top <- eventos[skill %in% top_skills & !es_primer_anio_observado & year %in% 2015:2017]
rm(eventos); gc()

outcome_inst <- eventos_top[, .(
  tasa_adopcion = mean(adopta_evento[has_skill_lag == 0L]),
  tasa_abandono = mean(abandona_evento[has_skill_lag == 1L])
), by = unitid]
rm(eventos_top); gc()

message(sprintf("  Instituciones con outcome 2015-2017: %d", nrow(outcome_inst)))

message("[4/6] Uniendo running variable + outcome...")
rd_data <- outcome_inst[doc2015, on = "unitid"]
rd_data <- rd_data[!is.na(tasa_adopcion) | !is.na(tasa_abandono)]
message(sprintf("  Muestra final para RD: %d instituciones", nrow(rd_data)))

message("[5/6] Estimando RD difusa (rdrobust) -- ADOPCION y ABANDONO...")

rd_adopcion <- rdrobust(y = rd_data$tasa_adopcion, x = rd_data$RSDoc, c = cutoff,
                         fuzzy = rd_data$is_r1)
rd_abandono <- rdrobust(y = rd_data$tasa_abandono, x = rd_data$RSDoc, c = cutoff,
                         fuzzy = rd_data$is_r1)
# Primera etapa: salto en P(is_r1=1) en el corte
rd_first_stage <- rdrobust(y = rd_data$is_r1, x = rd_data$RSDoc, c = cutoff)

message("\n--- PRIMERA ETAPA: salto en P(is_r1=1) en RSDoc=180 ---")
summary(rd_first_stage)

message("\n--- RD DIFUSA: ADOPCION ---")
summary(rd_adopcion)

message("\n--- RD DIFUSA: ABANDONO ---")
summary(rd_abandono)

message("[6/6] Guardando resultados y figura...")
dir.create("outputs/tables", showWarnings = FALSE, recursive = TRUE)
dir.create("outputs/figures", showWarnings = FALSE, recursive = TRUE)

sink("outputs/tables/tabla_rd_reclasificacion.txt")
cat("=== TEST DE MANIPULACION (densidad en el corte) ===\n")
print(summary(dens_test))
cat("\n=== PRIMERA ETAPA: P(is_r1=1) ===\n")
print(summary(rd_first_stage))
cat("\n=== RD DIFUSA: ADOPCION ===\n")
print(summary(rd_adopcion))
cat("\n=== RD DIFUSA: ABANDONO ===\n")
print(summary(rd_abandono))
sink()

pdf("outputs/figures/rd_reclasificacion.pdf", width = 8, height = 5)
rdplot(rd_data$is_r1, rd_data$RSDoc, c = cutoff,
       title = "Primera etapa: P(is_r1=1) segun RSDoc", x.label = "RSDoc (grados doctorales)", y.label = "P(is_r1)")
rdplot(rd_data$tasa_adopcion, rd_data$RSDoc, c = cutoff,
       title = "RD reducida: tasa de adopcion segun RSDoc", x.label = "RSDoc", y.label = "Tasa de adopcion")
rdplot(rd_data$tasa_abandono, rd_data$RSDoc, c = cutoff,
       title = "RD reducida: tasa de abandono segun RSDoc", x.label = "RSDoc", y.label = "Tasa de abandono")
dev.off()

message("Listo: outputs/tables/tabla_rd_reclasificacion.txt y outputs/figures/rd_reclasificacion.pdf")
