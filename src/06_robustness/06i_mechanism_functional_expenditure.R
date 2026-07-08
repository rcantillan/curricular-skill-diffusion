# ==============================================================================
# SCRIPT: 06i_mechanism_functional_expenditure.R
# OBJETIVO: Testear, para CADA categoria de gasto funcional (no solo
#           Instruccion, que ya se probo sin efecto en 06h), si declina mas
#           en instituciones con mayor dependencia de fondos estatales tras
#           2009 -- para identificar el canal especifico del mecanismo de
#           restriccion de recursos detectado en el resultado curricular.
#
# AUTOR: Roberto Cantillan Carrasco
# FECHA: Julio 2026
# ==============================================================================

library(data.table)
library(fixest)

dir_interim <- "data/interim"

message("[1/3] Cargando baseline de dependencia estatal y gasto funcional...")
finance <- fread(file.path(dir_interim, "ipeds_finance_state_approp_panel.csv"))
baseline <- finance[year %in% 2005:2007, .(baseline_share = mean(state_approp_share, na.rm = TRUE), n = .N), by = unitid]
baseline <- baseline[n >= 2]

funcional <- fread(file.path(dir_interim, "ipeds_functional_expenditure_panel.csv"))
funcional <- baseline[, .(unitid, baseline_share)][funcional, on = "unitid"]
funcional <- funcional[!is.na(baseline_share)]
funcional[, `:=`(baseline_share_z = as.numeric(scale(baseline_share)), post2009 = as.integer(year >= 2009))]

categorias <- c("instruccion", "investigacion", "servicio_publico", "apoyo_academico",
                 "servicios_estudiantiles", "apoyo_institucional", "operacion_mantenimiento",
                 "becas_ayudas", "empresas_auxiliares", "gasto_total")

message("[2/3] Estimando efecto sobre log(gasto) para cada categoria funcional...")
resultados <- list()
for (cat in categorias) {
  dt_cat <- copy(funcional)
  dt_cat[, gasto := get(cat)]
  dt_cat <- dt_cat[!is.na(gasto) & gasto > 0]
  dt_cat[, log_gasto := log(gasto)]
  # Winsorizar 1%/99% para evitar que errores de reporte dominen el ajuste
  q <- quantile(dt_cat$log_gasto, c(0.01, 0.99), na.rm = TRUE)
  dt_cat <- dt_cat[log_gasto >= q[1] & log_gasto <= q[2]]

  m <- tryCatch(
    feols(log_gasto ~ post2009 * baseline_share_z | unitid + year, data = dt_cat, cluster = ~unitid),
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

message("\n--- RESULTADOS: efecto de dependencia estatal x post-2009 sobre CADA categoria de gasto ---")
print(tabla_resultados)

message("[3/3] Guardando resultados...")
dir.create("outputs/tables", showWarnings = FALSE, recursive = TRUE)
fwrite(tabla_resultados, "outputs/tables/tabla_mecanismo_gasto_funcional.csv")
message("Listo: outputs/tables/tabla_mecanismo_gasto_funcional.csv")
