# ==============================================================================
# SCRIPT: 06l_recession_shock_yoy_appropriations.R
# OBJETIVO: Segunda prueba del mecanismo de recursos, INDEPENDIENTE del
#           evento unico de la recesion 2008-2009 (06h). En vez de una
#           intensidad de tratamiento fija (dependencia pre-2008) x un
#           evento comun, se explota la variacion AÑO A AÑO en apropiaciones
#           estatales reales de cada institucion a lo largo de TODO el panel
#           (2002-2017) -- shocks de financiamiento en cualquier año, no
#           solo alrededor de la Gran Recesion.
#
# DISEÑO: log(apropiacion estatal real) rezagada un año, con efectos fijos
# de institucion y año. Si el mecanismo de recursos es general (no un
# artefacto especifico de 2008), instituciones que reciben un RECORTE mayor
# en su apropiacion de un año a otro deberian mostrar menor adopcion y
# menor abandono el año siguiente, en cualquier punto del panel.
#
# AUTOR: Roberto Cantillan Carrasco
# FECHA: Julio 2026
# ==============================================================================

library(data.table)
library(fixest)

dir_interim <- "data/interim"

message("[1/6] Construyendo cambio año-a-año en apropiaciones estatales reales...")
finance <- fread(file.path(dir_interim, "ipeds_finance_state_approp_panel.csv"))
finance <- finance[state_approp > 0]
finance[, log_approp := log(state_approp)]
setorder(finance, unitid, year)
finance[, log_approp_lag := shift(log_approp), by = unitid]
finance[, cambio_approp := log_approp - log_approp_lag]  # crecimiento log año a año
finance <- finance[!is.na(cambio_approp) & is.finite(cambio_approp)]
# Winsorizar 1%/99% para evitar que errores de reporte dominen
q <- quantile(finance$cambio_approp, c(0.01, 0.99), na.rm = TRUE)
finance <- finance[cambio_approp >= q[1] & cambio_approp <= q[2]]
finance[, cambio_approp_z := as.numeric(scale(cambio_approp))]

message(sprintf("  Observaciones institucion-año con cambio valido: %s", format(nrow(finance), big.mark = ",")))
print(summary(finance$cambio_approp))

message("[2/6] Cargando eventos de adopcion/abandono y skills de frontera...")
metricas_frontera <- readRDS(file.path(dir_interim, "metricas_frontera_anual.rds"))
top_skills <- readRDS(file.path(dir_interim, "top_skills_baseline.rds"))

eventos <- readRDS(file.path(dir_interim, "adoption_abandonment_events.rds"))
eventos_top <- eventos[skill %in% top_skills & es_primer_anio_observado == FALSE]
rm(eventos); gc()

panel_maestro <- readRDS(file.path(dir_interim, "panel_maestro_curricular_2000_2017.rds"))
base_grid <- unique(panel_maestro[, .(unitid, fos, year, is_r1)], by = c("unitid", "fos", "year"))
rm(panel_maestro); gc()

panel_exposicion <- readRDS(file.path(dir_interim, "panel_exposicion_final.rds"))
vars_exposicion <- panel_exposicion[skill %in% top_skills, .(unitid, fos, year_lagged, skill, exp_elite, exp_base)]
setnames(vars_exposicion, "year_lagged", "year")
vars_exposicion <- unique(vars_exposicion, by = c("unitid", "fos", "year", "skill"))
rm(panel_exposicion); gc()

message("[3/6] Construyendo risk sets con el cambio de apropiacion REZAGADO (t-1 -> evento en t)...")
finance_lag <- copy(finance[, .(unitid, year, cambio_approp_z)])
finance_lag[, year := year + 1L]  # el cambio observado en t-1 predice el evento en t
setnames(finance_lag, "cambio_approp_z", "cambio_approp_lag_z")

construir_risk_set <- function(eventos_dt, evento_col) {
  rs <- merge(eventos_dt, base_grid, by = c("unitid", "fos", "year"), all.x = TRUE)
  rs <- merge(rs, vars_exposicion, by = c("unitid", "fos", "year", "skill"), all.x = TRUE)
  rs[is.na(exp_elite), exp_elite := 0]
  rs[is.na(exp_base), exp_base := 0]
  rs <- merge(rs, finance_lag, by = c("unitid", "year"))  # inner join: solo con dato de finanzas
  rs[, evento := get(evento_col)]
  rs[, `:=`(
    exp_elite_z = as.numeric(scale(exp_elite)),
    exp_base_z  = as.numeric(scale(exp_base))
  )]
  rs
}

rs_adopcion <- construir_risk_set(eventos_top[has_skill_lag == 0L], "adopta_evento")
rs_abandono <- construir_risk_set(eventos_top[has_skill_lag == 1L], "abandona_evento")
message(sprintf("  Risk set adopcion: %s | Risk set abandono: %s",
                format(nrow(rs_adopcion), big.mark = ","), format(nrow(rs_abandono), big.mark = ",")))

rm(eventos_top, base_grid, vars_exposicion)
gc()

message("[4/6] Estimando efecto del cambio año-a-año en apropiaciones sobre adopcion/abandono...")

modelo_adopcion <- feols(
  evento ~ cambio_approp_lag_z + exp_elite_z + exp_base_z | unitid + fos + year,
  data = rs_adopcion, cluster = ~unitid
)
modelo_abandono <- feols(
  evento ~ cambio_approp_lag_z + exp_elite_z + exp_base_z | unitid + fos + year,
  data = rs_abandono, cluster = ~unitid
)

message("\n--- SEGUNDO DISEÑO DE RECURSOS: cambio año-a-año en apropiaciones -> ADOPCION ---")
print(summary(modelo_adopcion))
message("\n--- SEGUNDO DISEÑO DE RECURSOS: cambio año-a-año en apropiaciones -> ABANDONO ---")
print(summary(modelo_abandono))

message("[5/6] Robustez: excluyendo la ventana 2008-2011 para verificar que el efecto no depende solo de la recesion...")
rs_adopcion_sin_recesion <- rs_adopcion[!year %in% 2008:2011]
rs_abandono_sin_recesion <- rs_abandono[!year %in% 2008:2011]

modelo_adopcion_sr <- feols(
  evento ~ cambio_approp_lag_z + exp_elite_z + exp_base_z | unitid + fos + year,
  data = rs_adopcion_sin_recesion, cluster = ~unitid
)
modelo_abandono_sr <- feols(
  evento ~ cambio_approp_lag_z + exp_elite_z + exp_base_z | unitid + fos + year,
  data = rs_abandono_sin_recesion, cluster = ~unitid
)
message("\n--- EXCLUYENDO 2008-2011: ADOPCION ---")
print(summary(modelo_adopcion_sr))
message("\n--- EXCLUYENDO 2008-2011: ABANDONO ---")
print(summary(modelo_abandono_sr))

message("[6/6] Guardando resultados...")
dir.create("outputs/tables", showWarnings = FALSE, recursive = TRUE)
etable(modelo_adopcion, modelo_abandono, modelo_adopcion_sr, modelo_abandono_sr,
       headers = list("Adopcion (todo el panel)", "Abandono (todo el panel)",
                       "Adopcion (sin 2008-2011)", "Abandono (sin 2008-2011)"),
       file = "outputs/tables/tabla_segundo_diseno_recursos.tex",
       title = "Segundo diseno de recursos: cambio año a año en apropiaciones estatales (independiente de 2008)")
message("Listo: outputs/tables/tabla_segundo_diseno_recursos.tex")
