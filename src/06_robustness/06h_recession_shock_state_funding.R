# ==============================================================================
# SCRIPT: 06h_recession_shock_state_funding.R
# OBJETIVO: Reemplazar el proxy binario publica/privada de 06g por la
#           dependencia REAL de financiamiento estatal (IPEDS Finance,
#           01e_build_state_appropriations_panel.R): la participacion de
#           apropiaciones estatales en los ingresos totales de la
#           institucion, promediada en el periodo PRE-recesion (2005-2007).
#           Instituciones con mayor dependencia estatal pre-crisis estuvieron
#           mas expuestas al recorte presupuestario de 2008-2012 -- una
#           medida continua de "intensidad de tratamiento", no un corte
#           binario publica/privada que mezcla muchas otras diferencias
#           institucionales.
#
# DISEÑO: DiD con intensidad continua de tratamiento (evento comun en 2009,
# intensidad = dependencia de financiamiento estatal pre-crisis, estandar
# en la literatura de shocks agregados con exposicion heterogenea -- ej.
# Bartik). Como el TIMING del shock es el MISMO para todas las unidades (no
# escalonado), el TWFE estandar es apropiado aqui (no aplica la critica de
# Goodman-Bacon a comparaciones prohibidas, que es especifica de timing
# escalonado).
#
# Se agrega ademas gasto en instruccion (F1C011, solo publicas) como
# verificacion DIRECTA del mecanismo: si el canal es realmente restriccion
# de recursos, el gasto en instruccion deberia caer mas en las instituciones
# mas dependientes de fondos estatales, en el mismo periodo.
#
# AUTOR: Roberto Cantillan Carrasco
# FECHA: Julio 2026
# ==============================================================================

library(data.table)
library(fixest)

setDTthreads(threads = min(4L, parallel::detectCores() - 2L))

dir_interim <- "data/interim"

message("[1/7] Construyendo dependencia de financiamiento estatal PRE-recesion (2005-2007)...")
finance <- fread(file.path(dir_interim, "ipeds_finance_state_approp_panel.csv"))
baseline <- finance[year %in% 2005:2007, .(
  baseline_share = mean(state_approp_share, na.rm = TRUE),
  n_anios = .N
), by = unitid]
baseline <- baseline[n_anios >= 2]  # exigir al menos 2 de los 3 anios para un promedio razonable

message(sprintf("  Instituciones con baseline de dependencia estatal: %d", nrow(baseline)))
message("  Distribucion:")
print(summary(baseline$baseline_share))

message("[2/7] Cargando eventos de adopcion/abandono y skills de frontera...")
metricas_frontera <- readRDS(file.path(dir_interim, "metricas_frontera_anual.rds"))
top_skills <- readRDS("data/interim/top_skills_baseline.rds")  # FIX: fijado solo con base 2000-2001

eventos <- readRDS(file.path(dir_interim, "adoption_abandonment_events.rds"))
eventos_top <- eventos[skill %in% top_skills & !es_primer_anio_observado]
rm(eventos); gc()

panel_maestro <- readRDS(file.path(dir_interim, "panel_maestro_curricular_2000_2017.rds"))
base_grid <- unique(panel_maestro[, .(unitid, fos, year, is_r1)], by = c("unitid", "fos", "year"))
rm(panel_maestro); gc()

panel_exposicion <- readRDS(file.path(dir_interim, "panel_exposicion_final.rds"))
vars_exposicion <- panel_exposicion[skill %in% top_skills, .(unitid, fos, year_lagged, skill, exp_elite, exp_base)]
setnames(vars_exposicion, "year_lagged", "year")
vars_exposicion <- unique(vars_exposicion, by = c("unitid", "fos", "year", "skill"))
rm(panel_exposicion); gc()

message("[3/7] Construyendo risk sets con dependencia estatal adjunta...")

construir_risk_set <- function(eventos_dt, evento_col) {
  rs <- merge(eventos_dt, base_grid, by = c("unitid", "fos", "year"), all.x = TRUE)
  rs <- merge(rs, vars_exposicion, by = c("unitid", "fos", "year", "skill"), all.x = TRUE)
  rs[is.na(exp_elite), exp_elite := 0]
  rs[is.na(exp_base), exp_base := 0]
  rs <- merge(rs, baseline[, .(unitid, baseline_share)], by = "unitid", all.x = FALSE)  # inner join: solo con dato de finanzas
  rs[, evento := get(evento_col)]
  rs[, `:=`(
    exp_elite_z = as.numeric(scale(exp_elite)),
    exp_base_z  = as.numeric(scale(exp_base)),
    baseline_share_z = as.numeric(scale(baseline_share)),
    post2009 = as.integer(year >= 2009)
  )]
  rs
}

rs_adopcion <- construir_risk_set(eventos_top[has_skill_lag == 0L], "adopta_evento")
rs_abandono <- construir_risk_set(eventos_top[has_skill_lag == 1L], "abandona_evento")
message(sprintf("  Risk set adopcion: %s | Risk set abandono: %s",
                format(nrow(rs_adopcion), big.mark = ","), format(nrow(rs_abandono), big.mark = ",")))

rm(eventos_top, base_grid, vars_exposicion)
gc()

message("[4/7] Estimando DiD con intensidad continua (TWFE)...")

modelo_did_adopcion <- feols(
  evento ~ post2009 * baseline_share_z + exp_elite_z + exp_base_z | unitid + fos + year,
  data = rs_adopcion, cluster = ~unitid
)
modelo_did_abandono <- feols(
  evento ~ post2009 * baseline_share_z + exp_elite_z + exp_base_z | unitid + fos + year,
  data = rs_abandono, cluster = ~unitid
)

message("[5/7] Estimando version dinamica (año x intensidad, referencia 2008)...")
modelo_dyn_adopcion <- feols(
  evento ~ i(year, baseline_share_z, ref = 2008) + exp_elite_z + exp_base_z | unitid + fos + year,
  data = rs_adopcion, cluster = ~unitid
)
modelo_dyn_abandono <- feols(
  evento ~ i(year, baseline_share_z, ref = 2008) + exp_elite_z + exp_base_z | unitid + fos + year,
  data = rs_abandono, cluster = ~unitid
)

message("\n--- DiD INTENSIDAD CONTINUA: ADOPCION ---")
print(summary(modelo_did_adopcion))
message("\n--- DiD INTENSIDAD CONTINUA: ABANDONO ---")
print(summary(modelo_did_abandono))

message("[6/7] Verificacion DIRECTA del mecanismo: gasto en instruccion (solo publicas)...")
inst_year <- finance[form_type == "F1A" & !is.na(gasto_instruccion) & gasto_instruccion > 0,
                      .(unitid, year, gasto_instruccion, total_revenue)]
inst_year <- baseline[, .(unitid, baseline_share)][inst_year, on = "unitid"]
inst_year[, log_gasto_instruccion := log(gasto_instruccion)]
inst_year[, `:=`(baseline_share_z = as.numeric(scale(baseline_share)), post2009 = as.integer(year >= 2009))]

modelo_mecanismo <- feols(
  log_gasto_instruccion ~ post2009 * baseline_share_z | unitid + year,
  data = inst_year, cluster = ~unitid
)
message("\n--- MECANISMO: efecto sobre log(gasto en instruccion), solo publicas ---")
print(summary(modelo_mecanismo))

message("[7/7] Guardando resultados y figuras...")
dir.create("outputs/tables", showWarnings = FALSE, recursive = TRUE)
dir.create("outputs/figures", showWarnings = FALSE, recursive = TRUE)

etable(modelo_did_adopcion, modelo_did_abandono, modelo_mecanismo,
       headers = list("Adopcion", "Abandono", "log(Gasto Instruccion)"),
       file = "outputs/tables/tabla_recesion_financiamiento_real.tex",
       title = "DiD con dependencia real de financiamiento estatal (IPEDS Finance): adopcion, abandono y mecanismo")

pdf("outputs/figures/recesion_financiamiento_real.pdf", width = 9, height = 5)
iplot(modelo_dyn_adopcion, main = "Efecto dinamico de la dependencia estatal x año sobre ADOPCION", xlab = "Año (ref. 2008)")
iplot(modelo_dyn_abandono, main = "Efecto dinamico de la dependencia estatal x año sobre ABANDONO", xlab = "Año (ref. 2008)")
dev.off()

message("Listo: outputs/tables/tabla_recesion_financiamiento_real.tex y outputs/figures/recesion_financiamiento_real.pdf")
