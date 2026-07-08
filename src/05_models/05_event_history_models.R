# ==============================================================================
# SCRIPT: 05_event_history_models.R
# OBJETIVO: Estimacion de modelos de difusion curricular en tiempo discreto,
#           separando ADOPCION y ABANDONO como dos hazards distintos.
#
# REDISEÑO COMPLETO (julio 2026):
#   1. "Adopcion" ya no es score>0 a nivel syllabus (saturado, ~99%). Ahora
#      viene de 03c, derivado de Revealed Comparative Advantage (RCA>=1) a
#      nivel celda (unitid x fos), tal como especifica el README original.
#   2. Se estiman DOS hazards en vez de uno solo con absorbing-state:
#        Hazard de ADOPCION: risk set = celda-skill-año con has_skill_lag==0
#          (no tenia el skill el año anterior). Evento = adopta_evento.
#        Hazard de ABANDONO: risk set = celda-skill-año con has_skill_lag==1
#          (tenia el skill el año anterior). Evento = abandona_evento.
#      Esto permite re-adopcion tras un abandono (spells multiples), a
#      diferencia del diseño anterior que sacaba a la celda del risk set
#      para siempre tras la primera adopcion.
#   3. Cada hazard se estima con DOS especificaciones de estatus (binaria vs.
#      gradiente institucional+disciplinar), como ya se hizo antes.
#
# Depende de 02 (panel maestro con is_r1/prestige_tier_num/field_status_index),
# 03c (eventos de adopcion/abandono), 03d (skills de frontera) y 04
# (exposicion estratificada, ahora tambien basada en RCA).
#
# AUTOR: Roberto Cantillan Carrasco
# FECHA: Julio 2026
# ==============================================================================

library(data.table)
library(fixest)

setDTthreads(threads = min(4L, parallel::detectCores() - 2L))

dir_interim <- "data/interim"
path_maestro  <- file.path(dir_interim, "panel_maestro_curricular_2000_2017.rds")
path_frontera <- file.path(dir_interim, "metricas_frontera_anual.rds")
path_exposure <- file.path(dir_interim, "panel_exposicion_final.rds")
path_eventos  <- file.path(dir_interim, "adoption_abandonment_events.rds")

message("Cargando matrices de datos...")
panel_maestro <- readRDS(path_maestro)
panel_exposicion <- readRDS(path_exposure)
metricas_frontera <- readRDS(path_frontera)
eventos <- readRDS(path_eventos)

# Top 100 skills de frontera por asimetria de estatus (RCA-based, ver 03d)
top_skills <- readRDS("data/interim/top_skills_baseline.rds")  # FIX: fijado solo con base 2000-2001, ver docs/replication_notes

message("Filtrando eventos a las Top 100 habilidades de frontera...")
eventos_top <- eventos[skill %in% top_skills & !es_primer_anio_observado]

# Variables de estatus por celda-año (institucion + disciplina)
base_grid <- unique(panel_maestro[, .(unitid, fos, year, is_r1, prestige_tier_num, field_status_index)],
                     by = c("unitid", "fos", "year"))

# Exposicion rezagada (t-1 -> t), ya viene de 04 con base RCA
vars_exposicion <- panel_exposicion[skill %in% top_skills, .(unitid, fos, year_lagged, skill, exp_elite, exp_base)]
setnames(vars_exposicion, "year_lagged", "year")
vars_exposicion <- unique(vars_exposicion, by = c("unitid", "fos", "year", "skill"))

construir_risk_set <- function(eventos_dt, evento_col) {
  rs <- merge(eventos_dt, base_grid, by = c("unitid", "fos", "year"), all.x = TRUE)
  rs <- merge(rs, vars_exposicion, by = c("unitid", "fos", "year", "skill"), all.x = TRUE)
  rs[is.na(exp_elite), exp_elite := 0]
  rs[is.na(exp_base), exp_base := 0]
  rs[, evento := get(evento_col)]
  rs[, `:=`(
    exp_elite_z = as.numeric(scale(exp_elite)),
    exp_base_z  = as.numeric(scale(exp_base)),
    field_status_index_z = as.numeric(scale(field_status_index))
  )]
  rs
}

message("Construyendo risk set de ADOPCION (celdas sin el skill el año anterior)...")
risk_set_adopcion <- construir_risk_set(eventos_top[has_skill_lag == 0L], "adopta_evento")
message(sprintf("  Observaciones: %s | Eventos de adopcion: %s",
                format(nrow(risk_set_adopcion), big.mark=","),
                format(sum(risk_set_adopcion$evento), big.mark=",")))

message("Construyendo risk set de ABANDONO (celdas con el skill el año anterior)...")
risk_set_abandono <- construir_risk_set(eventos_top[has_skill_lag == 1L], "abandona_evento")
message(sprintf("  Observaciones: %s | Eventos de abandono: %s",
                format(nrow(risk_set_abandono), big.mark=","),
                format(sum(risk_set_abandono$evento), big.mark=",")))

rm(panel_maestro, panel_exposicion, eventos, eventos_top)
gc()

message("\nEstimando modelos de ADOPCION...")

modelo_adopcion_binario <- feglm(
  evento ~ exp_elite_z + exp_base_z + is_r1 | year + fos,
  data = risk_set_adopcion, family = binomial(link = "logit")
)
modelo_adopcion_gradiente <- feglm(
  evento ~ exp_elite_z + exp_base_z + prestige_tier_num + field_status_index_z | year + fos,
  data = risk_set_adopcion, family = binomial(link = "logit")
)

message("Estimando modelos de ABANDONO...")

modelo_abandono_binario <- feglm(
  evento ~ exp_elite_z + exp_base_z + is_r1 | year + fos,
  data = risk_set_abandono, family = binomial(link = "logit")
)
modelo_abandono_gradiente <- feglm(
  evento ~ exp_elite_z + exp_base_z + prestige_tier_num + field_status_index_z | year + fos,
  data = risk_set_abandono, family = binomial(link = "logit")
)

message("\n--- ADOPCION: MODELO BINARIO (is_r1) ---")
print(summary(modelo_adopcion_binario))
message("\n--- ADOPCION: MODELO GRADIENTE ---")
print(summary(modelo_adopcion_gradiente))
message("\n--- ABANDONO: MODELO BINARIO (is_r1) ---")
print(summary(modelo_abandono_binario))
message("\n--- ABANDONO: MODELO GRADIENTE ---")
print(summary(modelo_abandono_gradiente))

dir.create("outputs/tables", showWarnings = FALSE, recursive = TRUE)
etable(modelo_adopcion_binario, modelo_adopcion_gradiente,
       modelo_abandono_binario, modelo_abandono_gradiente,
       headers = list("Adopcion (bin.)", "Adopcion (grad.)", "Abandono (bin.)", "Abandono (grad.)"),
       file = "outputs/tables/tabla_resultados_atc.tex",
       title = "Modelos de difusion curricular: adopcion vs. abandono, estatus binario vs. gradiente")
message("Tabla LaTeX comparativa (4 modelos) generada en outputs/tables/tabla_resultados_atc.tex")
