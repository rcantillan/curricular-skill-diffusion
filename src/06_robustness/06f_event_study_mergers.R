# ==============================================================================
# SCRIPT: 06f_event_study_mergers.R
# OBJETIVO: Cuarto diseño cuasi-experimental. Las fusiones institucionales
#           registradas en Carnegie (`MergeInto_Link`: una institucion es
#           absorbida por otra) son un shock exogeno al calendario curricular
#           de la institucion ABSORBENTE -- de un año a otro incorpora
#           facultad, programas y estudiantes de la institucion absorbida,
#           por razones tipicamente administrativas/financieras ajenas a la
#           estrategia curricular de la institucion receptora.
#
# TRATAMIENTO: año de la primera absorcion registrada para cada institucion
# (2000, 2005, 2010 o 2015 -- coincide con los ciclos de reconciliacion de
# Carnegie, no necesariamente la fecha exacta de la fusion real, limitacion
# a notar). 74 instituciones absorbentes con datos del Atlas, distribuidas
# de forma pareja entre las 4 cohortes (17-20 cada una). Control = 
# instituciones que nunca aparecen como absorbentes en la ventana 2000-2017.
#
# MISMO estimador Sun & Abraham (2021) que en 06, para comparabilidad directa.
#
# AUTOR: Roberto Cantillan Carrasco
# FECHA: Julio 2026
# ==============================================================================

library(data.table)
library(readxl)
library(fixest)

setDTthreads(threads = min(4L, parallel::detectCores() - 2L))

dir_interim <- "data/interim"

message("[1/6] Extrayendo cohortes de absorcion (fusiones) desde CCData...")
carnegie_raw <- as.data.table(read_excel(
  "data/raw/Longitudinal-Public-Data-File-1973-2021.xlsx", sheet = "CCData"))

merges <- carnegie_raw[!is.na(MergeInto_Link) & YEAR %in% 2000:2017,
                        .(C_UNITID = as.integer(C_UNITID), YEAR = as.integer(YEAR),
                          MergeInto_Link = as.integer(MergeInto_Link))]
cohortes_absorcion <- merges[, .(cohort_absorcion = min(YEAR)), by = .(unitid = MergeInto_Link)]

panel_maestro <- readRDS(file.path(dir_interim, "panel_maestro_curricular_2000_2017.rds"))
insts_con_atlas <- unique(panel_maestro[, .(unitid)])

trat_unitid <- cohortes_absorcion[insts_con_atlas, on = "unitid"]
trat_unitid[, cohort_absorcion := as.numeric(cohort_absorcion)]
trat_unitid[is.na(cohort_absorcion), cohort_absorcion := Inf]

message(sprintf("  Instituciones absorbentes (tratadas): %d | Control: %d",
                sum(is.finite(trat_unitid$cohort_absorcion)), sum(is.infinite(trat_unitid$cohort_absorcion))))
message("  Distribucion de cohortes:")
print(table(trat_unitid[is.finite(cohort_absorcion), cohort_absorcion]))

message("[2/6] Cargando eventos de adopcion/abandono y skills de frontera...")
metricas_frontera <- readRDS(file.path(dir_interim, "metricas_frontera_anual.rds"))
top_skills <- readRDS("data/interim/top_skills_baseline.rds")  # FIX: fijado solo con base 2000-2001

eventos <- readRDS(file.path(dir_interim, "adoption_abandonment_events.rds"))
eventos_top <- eventos[skill %in% top_skills & !es_primer_anio_observado]
rm(eventos); gc()

base_grid <- unique(panel_maestro[, .(unitid, fos, year, is_r1)], by = c("unitid", "fos", "year"))
rm(panel_maestro); gc()

panel_exposicion <- readRDS(file.path(dir_interim, "panel_exposicion_final.rds"))
vars_exposicion <- panel_exposicion[skill %in% top_skills, .(unitid, fos, year_lagged, skill, exp_elite, exp_base)]
setnames(vars_exposicion, "year_lagged", "year")
vars_exposicion <- unique(vars_exposicion, by = c("unitid", "fos", "year", "skill"))
rm(panel_exposicion); gc()

message("[3/6] Construyendo risk sets con cohorte de fusion adjunta...")

construir_risk_set <- function(eventos_dt, evento_col) {
  rs <- merge(eventos_dt, base_grid, by = c("unitid", "fos", "year"), all.x = TRUE)
  rs <- merge(rs, vars_exposicion, by = c("unitid", "fos", "year", "skill"), all.x = TRUE)
  rs[is.na(exp_elite), exp_elite := 0]
  rs[is.na(exp_base), exp_base := 0]
  rs <- merge(rs, trat_unitid, by = "unitid", all.x = TRUE)
  rs <- rs[!is.na(cohort_absorcion)]
  rs[, evento := get(evento_col)]
  rs[, `:=`(
    exp_elite_z = as.numeric(scale(exp_elite)),
    exp_base_z  = as.numeric(scale(exp_base))
  )]
  rs
}

rs_adopcion <- construir_risk_set(eventos_top[has_skill_lag == 0L], "adopta_evento")
rs_abandono <- construir_risk_set(eventos_top[has_skill_lag == 1L], "abandona_evento")

message(sprintf("  Risk set adopcion: %s filas | Risk set abandono: %s filas",
                format(nrow(rs_adopcion), big.mark = ","), format(nrow(rs_abandono), big.mark = ",")))

rm(eventos_top, base_grid, vars_exposicion, carnegie_raw, merges)
gc()

message("[4/6] Estimando event-study de ADOPCION (Sun & Abraham)...")
modelo_es_adopcion <- feols(
  evento ~ sunab(cohort_absorcion, year) + exp_elite_z + exp_base_z | unitid + fos + year,
  data = rs_adopcion, cluster = ~unitid
)

message("[5/6] Estimando event-study de ABANDONO (Sun & Abraham)...")
modelo_es_abandono <- feols(
  evento ~ sunab(cohort_absorcion, year) + exp_elite_z + exp_base_z | unitid + fos + year,
  data = rs_abandono, cluster = ~unitid
)

message("\n--- EVENT-STUDY FUSIONES: ADOPCION ---")
print(summary(modelo_es_adopcion))
message("\n--- ATT AGREGADO: ADOPCION ---")
print(summary(modelo_es_adopcion, agg = "att"))

message("\n--- EVENT-STUDY FUSIONES: ABANDONO ---")
print(summary(modelo_es_abandono))
message("\n--- ATT AGREGADO: ABANDONO ---")
print(summary(modelo_es_abandono, agg = "att"))

message("[6/6] Guardando resultados...")
dir.create("outputs/tables", showWarnings = FALSE, recursive = TRUE)
dir.create("outputs/figures", showWarnings = FALSE, recursive = TRUE)

etable(modelo_es_adopcion, modelo_es_abandono,
       headers = list("Adopcion", "Abandono"),
       file = "outputs/tables/tabla_event_study_fusiones.tex",
       title = "Event-study: fusiones institucionales (Sun & Abraham) sobre adopcion y abandono de skills de frontera")

pdf("outputs/figures/event_study_fusiones.pdf", width = 9, height = 5)
iplot(modelo_es_adopcion, main = "Efecto dinamico de la fusion (absorbente) sobre ADOPCION", xlab = "Anios relativos a la fusion")
iplot(modelo_es_abandono, main = "Efecto dinamico de la fusion (absorbente) sobre ABANDONO", xlab = "Anios relativos a la fusion")
dev.off()

message("Listo: outputs/tables/tabla_event_study_fusiones.tex y outputs/figures/event_study_fusiones.pdf")
