# ==============================================================================
# SCRIPT: 06k_mechanism_expenditure_per_fte.R
# OBJETIVO: Cerrar la pregunta abierta de 06i -- el gasto funcional NOMINAL
#           mostraba un patron dificil de interpretar porque no estaba
#           normalizado por matricula. Aqui se recalcula gasto POR ESTUDIANTE
#           FTE (01h) para cada categoria funcional, 2008-2017, y se
#           reestima el mismo DiD de dependencia estatal x post-2009.
#
# AUTOR: Roberto Cantillan Carrasco
# FECHA: Julio 2026
# ==============================================================================

library(data.table)
library(fixest)

dir_interim <- "data/interim"

message("[1/3] Cargando baseline, gasto funcional y matricula FTE...")
finance <- fread(file.path(dir_interim, "ipeds_finance_state_approp_panel.csv"))
baseline <- finance[year %in% 2005:2007, .(baseline_share = mean(state_approp_share, na.rm = TRUE), n = .N), by = unitid]
baseline <- baseline[n >= 2]

funcional <- fread(file.path(dir_interim, "ipeds_functional_expenditure_panel.csv"))
fte <- fread(file.path(dir_interim, "ipeds_fte_enrollment_panel.csv"))

dt <- merge(funcional, fte, by = c("unitid", "year"))
dt <- baseline[, .(unitid, baseline_share)][dt, on = "unitid"]
dt <- dt[!is.na(baseline_share) & fte_matricula > 0]

dt[, `:=`(baseline_share_z = as.numeric(scale(baseline_share)), post2009 = as.integer(year >= 2009))]

categorias <- c("instruccion", "investigacion", "servicio_publico", "apoyo_academico",
                 "servicios_estudiantiles", "apoyo_institucional", "operacion_mantenimiento",
                 "becas_ayudas", "empresas_auxiliares", "gasto_total")

message("[2/3] Estimando efecto sobre log(gasto POR FTE) para cada categoria...")
resultados <- list()
for (cat in categorias) {
  dt_cat <- copy(dt)
  dt_cat[, gasto_fte := get(cat) / fte_matricula]
  dt_cat <- dt_cat[!is.na(gasto_fte) & gasto_fte > 0]
  dt_cat[, log_gasto_fte := log(gasto_fte)]
  q <- quantile(dt_cat$log_gasto_fte, c(0.01, 0.99), na.rm = TRUE)
  dt_cat <- dt_cat[log_gasto_fte >= q[1] & log_gasto_fte <= q[2]]

  m <- tryCatch(
    feols(log_gasto_fte ~ post2009 * baseline_share_z | unitid + year, data = dt_cat, cluster = ~unitid),
    error = function(e) NULL
  )
  if (is.null(m)) next
  coefs <- coeftable(m)
  fila <- coefs[grepl("post2009:baseline_share_z", rownames(coefs)), , drop = FALSE]
  resultados[[cat]] <- data.table(
    categoria = cat, n = nrow(dt_cat), n_inst = uniqueN(dt_cat$unitid),
    estimate = fila[1, "Estimate"], se = fila[1, "Std. Error"], p = fila[1, "Pr(>|t|)"]
  )
}
tabla_resultados <- rbindlist(resultados)
setorder(tabla_resultados, p)

message("\n--- RESULTADOS: efecto de dependencia estatal x post-2009 sobre gasto POR FTE, cada categoria ---")
print(tabla_resultados)

message("[3/3] Guardando resultados...")
dir.create("outputs/tables", showWarnings = FALSE, recursive = TRUE)
fwrite(tabla_resultados, "outputs/tables/tabla_mecanismo_gasto_per_fte.csv")
message("Listo: outputs/tables/tabla_mecanismo_gasto_per_fte.csv")
