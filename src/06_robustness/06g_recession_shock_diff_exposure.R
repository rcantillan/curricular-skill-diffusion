# ==============================================================================
# SCRIPT: 06g_recession_shock_diff_exposure.R
# OBJETIVO: Quinto diseño cuasi-experimental. La Gran Recesion (2008-2010)
#           es un shock agregado, simultaneo para todo el sistema -- por si
#           solo no da variacion transversal. Pero afecto de forma MUY
#           desigual a instituciones publicas (dependientes de presupuesto
#           estatal, que se recorto duramente en casi todos los estados) vs.
#           privadas (expuestas mas bien a shocks de endowment/mercado
#           financiero, de otra naturaleza y magnitud). Se usa CONTROL
#           (publica/privada, ya en el panel Carnegie) como intensidad de
#           "tratamiento" en un diseño de diferencias-en-diferencias
#           alrededor de la recesion.
#
# NOTA IMPORTANTE SOBRE ALCANCE: esta es una version DELIBERADAMENTE MAS
# SIMPLE que la propuesta original (usar apropiaciones estatales por FTE de
# SHEEO como intensidad continua de exposicion). Se intento acceder al
# portal de datos de SHEEO (shef.sheeo.org/data-downloads) pero es una
# aplicacion interactiva (JS) sin archivos CSV/Excel estaticos accesibles
# por descarga automatizada en este entorno -- no se pudo construir la
# version con apropiaciones reales por estado sin ese archivo. Esta version
# usa publica/privada como proxy binario de exposicion, verificable con los
# datos que ya tenemos, en vez de fabricar cifras de apropiaciones estatales
# sin fuente verificada.
#
# DISEÑO: DiD con Sun & Abraham centrado en el shock (tratamiento = ser
# institucion PUBLICA, "tiempo" del shock = 2009, el año de mayor severidad
# de los recortes presupuestarios estatales documentados en la literatura
# de economia de la educacion superior). Grupo de control = instituciones
# privadas (nunca "tratadas" por este canal especifico).
#
# AUTOR: Roberto Cantillan Carrasco
# FECHA: Julio 2026
# ==============================================================================

library(data.table)
library(fixest)

setDTthreads(threads = min(4L, parallel::detectCores() - 2L))

dir_interim <- "data/interim"

message("[1/5] Cargando control publica/privada y definiendo tratamiento...")
carnegie <- fread(file.path(dir_interim, "carnegie_prestige_panel_2000_2017.csv"),
                   select = c("unitid", "year", "control"))
control_inst <- unique(carnegie[year == 2008, .(unitid, control)], by = "unitid")
# CONTROL Carnegie/IPEDS: 1 = Publica, 2 = Privada sin fines de lucro, 3 = Privada con fines de lucro
control_inst[, es_publica := as.integer(control == 1L)]
control_inst <- control_inst[!is.na(es_publica)]

message(sprintf("  Publicas: %d | Privadas: %d",
                sum(control_inst$es_publica == 1L), sum(control_inst$es_publica == 0L)))

# Tratamiento tipo evento unico (no escalonado): todas las publicas
# "tratadas" en 2009, todas las privadas nunca tratadas por este canal.
control_inst[, cohort_recesion := fifelse(es_publica == 1L, 2009, Inf)]

message("[2/5] Cargando eventos y construyendo risk sets (igual que 06/06f)...")
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

construir_risk_set <- function(eventos_dt, evento_col) {
  rs <- merge(eventos_dt, base_grid, by = c("unitid", "fos", "year"), all.x = TRUE)
  rs <- merge(rs, vars_exposicion, by = c("unitid", "fos", "year", "skill"), all.x = TRUE)
  rs[is.na(exp_elite), exp_elite := 0]
  rs[is.na(exp_base), exp_base := 0]
  rs <- merge(rs, control_inst[, .(unitid, cohort_recesion, es_publica)], by = "unitid", all.x = TRUE)
  rs <- rs[!is.na(cohort_recesion)]
  rs[, evento := get(evento_col)]
  rs[, `:=`(
    exp_elite_z = as.numeric(scale(exp_elite)),
    exp_base_z  = as.numeric(scale(exp_base))
  )]
  rs
}

message("[3/5] Construyendo risk sets...")
rs_adopcion <- construir_risk_set(eventos_top[has_skill_lag == 0L], "adopta_evento")
rs_abandono <- construir_risk_set(eventos_top[has_skill_lag == 1L], "abandona_evento")
message(sprintf("  Risk set adopcion: %s | Risk set abandono: %s",
                format(nrow(rs_adopcion), big.mark = ","), format(nrow(rs_abandono), big.mark = ",")))

rm(eventos_top, base_grid, vars_exposicion, carnegie)
gc()

message("[4/5] Estimando event-study (Sun & Abraham, tratamiento unico en 2009)...")
modelo_es_adopcion <- feols(
  evento ~ sunab(cohort_recesion, year) + exp_elite_z + exp_base_z | unitid + fos + year,
  data = rs_adopcion, cluster = ~unitid
)
modelo_es_abandono <- feols(
  evento ~ sunab(cohort_recesion, year) + exp_elite_z + exp_base_z | unitid + fos + year,
  data = rs_abandono, cluster = ~unitid
)

message("\n--- EVENT-STUDY GRAN RECESION (publica vs privada): ADOPCION ---")
print(summary(modelo_es_adopcion))
message("\n--- ATT AGREGADO: ADOPCION ---")
print(summary(modelo_es_adopcion, agg = "att"))

message("\n--- EVENT-STUDY GRAN RECESION (publica vs privada): ABANDONO ---")
print(summary(modelo_es_abandono))
message("\n--- ATT AGREGADO: ABANDONO ---")
print(summary(modelo_es_abandono, agg = "att"))

message("[5/5] Guardando resultados...")
dir.create("outputs/tables", showWarnings = FALSE, recursive = TRUE)
dir.create("outputs/figures", showWarnings = FALSE, recursive = TRUE)

etable(modelo_es_adopcion, modelo_es_abandono,
       headers = list("Adopcion", "Abandono"),
       file = "outputs/tables/tabla_event_study_recesion.tex",
       title = "Event-study: Gran Recesion 2009 (publica vs. privada) sobre adopcion y abandono de skills de frontera")

pdf("outputs/figures/event_study_recesion.pdf", width = 9, height = 5)
iplot(modelo_es_adopcion, main = "Efecto dinamico de la Gran Recesion (publica vs privada) sobre ADOPCION", xlab = "Anios relativos a 2009")
iplot(modelo_es_abandono, main = "Efecto dinamico de la Gran Recesion (publica vs privada) sobre ABANDONO", xlab = "Anios relativos a 2009")
dev.off()

message("Listo: outputs/tables/tabla_event_study_recesion.tex y outputs/figures/event_study_recesion.pdf")
