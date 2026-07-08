# ==============================================================================
# SCRIPT: 06j_mechanism_staffing.R
# OBJETIVO: Segunda pieza del mecanismo solicitada -- planta docente. Testear
#           si el TAMAÑO de la planta docente (headcount total de
#           "instructional staff") declina mas en instituciones dependientes
#           de fondos estatales tras 2009, como canal alternativo al gasto
#           en dolares (que en 06i mostro un patron dificil de interpretar
#           sin normalizar por matricula).
#
# AUTOR: Roberto Cantillan Carrasco
# FECHA: Julio 2026
# ==============================================================================

library(data.table)
library(fixest)

dir_interim <- "data/interim"

message("[1/3] Cargando baseline de dependencia estatal y planta docente...")
finance <- fread(file.path(dir_interim, "ipeds_finance_state_approp_panel.csv"))
baseline <- finance[year %in% 2005:2007, .(baseline_share = mean(state_approp_share, na.rm = TRUE), n = .N), by = unitid]
baseline <- baseline[n >= 2]

staff <- fread(file.path(dir_interim, "ipeds_instructional_staff_panel.csv"))
staff <- baseline[, .(unitid, baseline_share)][staff, on = "unitid"]
staff <- staff[!is.na(baseline_share) & !is.na(instructional_staff) & instructional_staff > 0]
staff[, log_staff := log(instructional_staff)]

q <- quantile(staff$log_staff, c(0.01, 0.99), na.rm = TRUE)
staff <- staff[log_staff >= q[1] & log_staff <= q[2]]

staff[, `:=`(baseline_share_z = as.numeric(scale(baseline_share)), post2009 = as.integer(year >= 2009))]

message(sprintf("  Observaciones: %d | Instituciones: %d", nrow(staff), uniqueN(staff$unitid)))

message("[2/3] Estimando efecto sobre log(planta docente)...")
modelo_nivel <- feols(log_staff ~ post2009 * baseline_share_z | unitid + year, data = staff, cluster = ~unitid)
modelo_dinamico <- feols(log_staff ~ i(year, baseline_share_z, ref = 2008) | unitid + year, data = staff, cluster = ~unitid)

message("\n--- MECANISMO: efecto sobre log(planta docente) ---")
print(summary(modelo_nivel))

message("\n--- VERSION DINAMICA (año x dependencia estatal) ---")
print(summary(modelo_dinamico))

message("[3/3] Guardando resultados...")
dir.create("outputs/tables", showWarnings = FALSE, recursive = TRUE)
dir.create("outputs/figures", showWarnings = FALSE, recursive = TRUE)

etable(modelo_nivel,
       file = "outputs/tables/tabla_mecanismo_planta_docente.tex",
       title = "Mecanismo: efecto de dependencia estatal x post-2009 sobre planta docente")

pdf("outputs/figures/mecanismo_planta_docente.pdf", width = 9, height = 5)
iplot(modelo_dinamico, main = "Efecto dinamico de dependencia estatal x año sobre planta docente", xlab = "Año (ref. 2008)")
dev.off()

message("Listo: outputs/tables/tabla_mecanismo_planta_docente.tex y outputs/figures/mecanismo_planta_docente.pdf")
