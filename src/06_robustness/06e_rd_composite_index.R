# ==============================================================================
# SCRIPT: 06e_rd_composite_index.R
# OBJETIVO: Corregir la RD fallida de 06c. El diagnostico fue que RSDoc solo
#           es una de varias variables que determinan la clasificacion real
#           de Carnegie, y por si sola no genera un salto lo bastante nitido
#           para que rdrobust lo identifique (primera etapa ~0, IC absurdos).
#
# FIX: construir un INDICE COMPUESTO (score de propension) prediciendo is_r1
# dentro de Group==Doctoral, vintage 2015, a partir de TODAS las variables
# continuas disponibles en CCData (RSDoc, DEGTOT, GRFTEnr, GRPTEnr, HCTTOT)
# via regresion logistica. El indice = predictor lineal (log-odds), con
# corte natural en 0 (probabilidad predicha = 0.5) -- no se busca el corte
# empiricamente sobre el outcome, se deriva del propio modelo de asignacion.
# Precision de clasificacion resultante: 89.2% (vs. la separacion mucho mas
# ruidosa de RSDoc solo). Densidad efectiva cerca del corte: 111
# instituciones dentro de +-2 log-odds (vs. ~40 antes).
#
# MISMA CAUTELA: esto sigue siendo una RD DIFUSA (el indice no determina el
# 100% de los casos -- 89.2% no 100%), y el indice se estima con los MISMOS
# datos que definen el tratamiento (es una aproximacion a la regla real de
# asignacion, no la regla exacta que uso Carnegie, que tambien pesa gasto en
# investigacion no disponible en este archivo).
#
# AUTOR: Roberto Cantillan Carrasco
# FECHA: Julio 2026
# ==============================================================================

library(data.table)
library(readxl)
library(rdrobust)
library(rddensity)

dir_interim <- "data/interim"

message("[1/6] Construyendo el indice compuesto de propension a ser R1...")
carnegie_raw <- as.data.table(read_excel(
  "data/raw/Longitudinal-Public-Data-File-1973-2021.xlsx", sheet = "CCData"))
doc2015 <- carnegie_raw[YEAR == 2015 & Group == 1, .(
  unitid = as.integer(C_UNITID), RSDoc = as.numeric(RSDoc), DEGTOT = as.numeric(DEGTOT),
  GRFTEnr = as.numeric(GRFTEnr), GRPTEnr = as.numeric(GRPTEnr), HCTTOT = as.numeric(HCTTOT),
  VALUE = as.integer(VALUE)
)]
doc2015 <- unique(doc2015[!is.na(unitid)], by = "unitid")
doc2015[, is_r1 := as.integer(VALUE == 15)]

modelo_indice <- glm(is_r1 ~ RSDoc + DEGTOT + GRFTEnr + GRPTEnr + HCTTOT, data = doc2015, family = binomial)
print(summary(modelo_indice))
doc2015[, indice := predict(modelo_indice, type = "link")]
precision <- mean(as.integer(predict(modelo_indice, type = "response") > 0.5) == doc2015$is_r1)
message(sprintf("  Precision de clasificacion del indice: %.1f%%", 100 * precision))
message(sprintf("  Instituciones dentro de +-2 log-odds del corte: %d",
                nrow(doc2015[abs(indice) < 2])))

cutoff <- 0

message("[2/6] Test de manipulacion sobre el indice compuesto...")
dens_test <- rddensity(doc2015$indice, c = cutoff)
print(summary(dens_test))

message("[3/6] Reconstruyendo panel institucion x año de tasas 2015-2017...")
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

message("[4/6] Uniendo indice + outcome...")
rd_data <- outcome_inst[doc2015, on = "unitid"]
rd_data <- rd_data[!is.na(tasa_adopcion) | !is.na(tasa_abandono)]
message(sprintf("  Muestra final para RD: %d instituciones", nrow(rd_data)))

message("[5/6] Estimando RD difusa (rdrobust) con indice compuesto...")

rd_first_stage <- rdrobust(y = rd_data$is_r1, x = rd_data$indice, c = cutoff)
rd_adopcion <- rdrobust(y = rd_data$tasa_adopcion, x = rd_data$indice, c = cutoff, fuzzy = rd_data$is_r1)
rd_abandono <- rdrobust(y = rd_data$tasa_abandono, x = rd_data$indice, c = cutoff, fuzzy = rd_data$is_r1)

message("\n--- PRIMERA ETAPA (indice compuesto): salto en P(is_r1=1) ---")
summary(rd_first_stage)

message("\n--- RD DIFUSA (indice compuesto): ADOPCION ---")
summary(rd_adopcion)

message("\n--- RD DIFUSA (indice compuesto): ABANDONO ---")
summary(rd_abandono)

message("[6/6] Guardando resultados y figuras...")
dir.create("outputs/tables", showWarnings = FALSE, recursive = TRUE)
dir.create("outputs/figures", showWarnings = FALSE, recursive = TRUE)

sink("outputs/tables/tabla_rd_indice_compuesto.txt")
cat("=== MODELO DEL INDICE (propension a is_r1) ===\n")
print(summary(modelo_indice))
cat(sprintf("\nPrecision de clasificacion: %.1f%%\n", 100 * precision))
cat("\n=== TEST DE MANIPULACION ===\n")
print(summary(dens_test))
cat("\n=== PRIMERA ETAPA ===\n")
print(summary(rd_first_stage))
cat("\n=== RD DIFUSA: ADOPCION ===\n")
print(summary(rd_adopcion))
cat("\n=== RD DIFUSA: ABANDONO ===\n")
print(summary(rd_abandono))
sink()

pdf("outputs/figures/rd_indice_compuesto.pdf", width = 8, height = 5)
rdplot(rd_data$is_r1, rd_data$indice, c = cutoff,
       title = "Primera etapa: P(is_r1=1) segun indice compuesto", x.label = "Indice (log-odds)", y.label = "P(is_r1)")
rdplot(rd_data$tasa_adopcion, rd_data$indice, c = cutoff,
       title = "RD reducida: tasa de adopcion", x.label = "Indice (log-odds)", y.label = "Tasa de adopcion")
rdplot(rd_data$tasa_abandono, rd_data$indice, c = cutoff,
       title = "RD reducida: tasa de abandono", x.label = "Indice (log-odds)", y.label = "Tasa de abandono")
dev.off()

message("Listo: outputs/tables/tabla_rd_indice_compuesto.txt y outputs/figures/rd_indice_compuesto.pdf")
