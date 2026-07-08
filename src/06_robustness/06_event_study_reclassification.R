# ==============================================================================
# SCRIPT: 06_event_study_reclassification.R
# OBJETIVO: Explotar la reclasificacion Carnegie como cuasi-experimento
#           natural para identificar el efecto CAUSAL de alcanzar estatus
#           elite (R1) sobre la velocidad de adopcion y abandono de skills
#           de frontera -- en vez de solo correlacionar exposicion con
#           adopcion (que sufre el "problema del reflejo" de Manski).
#
# LOGICA DEL EXPERIMENTO NATURAL
# --------------------------------
# La clasificacion Carnegie se revisa en ciclos fijos externos (2000, 2005,
# 2010, 2015...), no cuando cada institucion decide. El nivel de prestigio
# (`prestige_tier_num`, 0-3) de una institucion solo puede cambiar en esos
# anios. Usamos las transiciones LIMPIAS (`clean_promotion`/`clean_demotion`
# de 01a: la institucion sube/baja de nivel y NO revierte por el resto del
# panel -- excluye el "rebote de borde" tipo Univ. of Arkansas 2000-2010).
#
# DISEÑO: Sun & Abraham (2021) interaction-weighted estimator (via
# fixest::sunab), robusto al problema de comparaciones prohibidas en DiD
# escalonado (Goodman-Bacon). Cohortes = año de la primera promocion limpia
# (2005, 2010 o 2015). Grupo de control = instituciones que NUNCA tuvieron
# una promocion limpia en la ventana 2000-2017 (excluyendo las que ya eran
# R1 desde el inicio del panel, que no aportan variacion pre-tratamiento).
#
# Efectos dinamicos (leads/lags) sobre dos outcomes: hazard de ADOPCION y
# hazard de ABANDONO de skills de frontera, a nivel celda (unitid x fos).
#
# AUTOR: Roberto Cantillan Carrasco
# FECHA: Julio 2026
# ==============================================================================

library(data.table)
library(fixest)

setDTthreads(threads = min(4L, parallel::detectCores() - 2L))

dir_interim <- "data/interim"

message("[1/6] Cargando panel Carnegie y construyendo cohortes de tratamiento...")
carnegie <- fread(file.path(dir_interim, "carnegie_prestige_panel_2000_2017.csv"))
setorder(carnegie, unitid, year)

# Cohorte de PROMOCION limpia: primer anio (si existe) en que la institucion
# sube de nivel y no revierte. Excluir "always-treated" (tier==3 desde 2000).
cohortes_promocion <- carnegie[clean_promotion == TRUE, .(cohort_promocion = min(year)), by = unitid]
siempre_r1 <- carnegie[year == 2000 & prestige_tier_num == 3, unique(unitid)]

trat_unitid <- unique(carnegie[, .(unitid)])
trat_unitid <- cohortes_promocion[trat_unitid, on = "unitid"]
trat_unitid <- trat_unitid[!unitid %in% siempre_r1]
# IMPORTANTE: forzar a double ANTES de asignar Inf -- si la columna queda
# como integer (heredado de min(year)), Inf se trunca silenciosamente a NA.
trat_unitid[, cohort_promocion := as.numeric(cohort_promocion)]
# fixest::sunab espera Inf (o NA tratado como nunca-tratado) para el grupo de control
trat_unitid[is.na(cohort_promocion), cohort_promocion := Inf]

message(sprintf("  Instituciones tratadas (cohortes 2005/2010/2015): %d", sum(is.finite(trat_unitid$cohort_promocion))))
message(sprintf("  Instituciones control (nunca promovidas limpiamente, no siempre-R1): %d", sum(is.infinite(trat_unitid$cohort_promocion))))

message("[2/6] Cargando eventos de adopcion/abandono y skills de frontera...")
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

message("[3/6] Construyendo risk sets con cohorte de tratamiento adjunta...")

construir_risk_set_es <- function(eventos_dt, evento_col) {
  rs <- merge(eventos_dt, base_grid, by = c("unitid", "fos", "year"), all.x = TRUE)
  rs <- merge(rs, vars_exposicion, by = c("unitid", "fos", "year", "skill"), all.x = TRUE)
  rs[is.na(exp_elite), exp_elite := 0]
  rs[is.na(exp_base), exp_base := 0]
  rs <- merge(rs, trat_unitid, by = "unitid", all.x = TRUE)
  rs <- rs[!is.na(cohort_promocion)]  # excluye siempre-R1
  rs[, evento := get(evento_col)]
  rs[, `:=`(
    exp_elite_z = as.numeric(scale(exp_elite)),
    exp_base_z  = as.numeric(scale(exp_base))
  )]
  rs
}

rs_adopcion <- construir_risk_set_es(eventos_top[has_skill_lag == 0L], "adopta_evento")
rs_abandono <- construir_risk_set_es(eventos_top[has_skill_lag == 1L], "abandona_evento")

message(sprintf("  Risk set adopcion: %s filas | Risk set abandono: %s filas",
                format(nrow(rs_adopcion), big.mark = ","), format(nrow(rs_abandono), big.mark = ",")))

rm(eventos_top, base_grid, vars_exposicion, carnegie)
gc()

message("[4/6] Estimando event-study de ADOPCION (Sun & Abraham)...")
modelo_es_adopcion <- feols(
  evento ~ sunab(cohort_promocion, year) + exp_elite_z + exp_base_z | unitid + fos + year,
  data = rs_adopcion,
  cluster = ~unitid
)

message("[5/6] Estimando event-study de ABANDONO (Sun & Abraham)...")
modelo_es_abandono <- feols(
  evento ~ sunab(cohort_promocion, year) + exp_elite_z + exp_base_z | unitid + fos + year,
  data = rs_abandono,
  cluster = ~unitid
)

message("\n--- EVENT-STUDY: ADOPCION (efecto dinamico de la promocion a R1) ---")
print(summary(modelo_es_adopcion))
message("\n--- ATT AGREGADO: ADOPCION ---")
print(summary(modelo_es_adopcion, agg = "att"))

message("\n--- EVENT-STUDY: ABANDONO (efecto dinamico de la promocion a R1) ---")
print(summary(modelo_es_abandono))
message("\n--- ATT AGREGADO: ABANDONO ---")
print(summary(modelo_es_abandono, agg = "att"))

message("[6/6] Guardando resultados...")
dir.create("outputs/tables", showWarnings = FALSE, recursive = TRUE)
dir.create("outputs/figures", showWarnings = FALSE, recursive = TRUE)

etable(modelo_es_adopcion, modelo_es_abandono,
       headers = list("Adopcion", "Abandono"),
       file = "outputs/tables/tabla_event_study_reclasificacion.tex",
       title = "Event-study: reclasificacion Carnegie (Sun & Abraham) sobre adopcion y abandono de skills de frontera")

pdf("outputs/figures/event_study_reclasificacion.pdf", width = 9, height = 5)
iplot(modelo_es_adopcion, main = "Efecto dinamico de la promocion a R1 sobre ADOPCION", xlab = "Anios relativos a la promocion")
iplot(modelo_es_abandono, main = "Efecto dinamico de la promocion a R1 sobre ABANDONO", xlab = "Anios relativos a la promocion")
dev.off()

message("Listo: outputs/tables/tabla_event_study_reclasificacion.tex y outputs/figures/event_study_reclasificacion.pdf")
