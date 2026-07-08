# ==============================================================================
# SCRIPT: 07a_descriptive_diffusion_gradients.R
# OBJETIVO: Caracterizar DESCRIPTIVAMENTE la difusion curricular estratificada
#           -- analogo a la Fig. 1 del paper de ocupaciones -- cruzando la
#           taxonomia de 3 clases de skills (Socio-Cognitiva General,
#           Socio-Cognitiva Especializada, Fisico-Sensorial) con el nivel de
#           prestigio institucional y con el estatus disciplinar.
#
# Usa la matriz de eventos completa (todos los años, no solo top-100
# frontera) para dar una caracterizacion amplia del fenomeno, no acotada a
# las skills usadas en los modelos causales.
#
# AUTOR: Roberto Cantillan Carrasco
# FECHA: Julio 2026
# ==============================================================================

library(data.table)

dir_interim <- "data/interim"

message("[1/4] Cargando taxonomia, eventos de adopcion/abandono y atributos institucionales...")
tax <- fread(file.path(dir_interim, "skill_taxonomy.csv"), select = c("skill", "clase"))
tax <- tax[clase != "Socio-Cognitiva (sin c_s, prevalencia extrema)"]

eventos <- readRDS(file.path(dir_interim, "adoption_abandonment_events.rds"))
eventos <- eventos[es_primer_anio_observado == FALSE]
eventos <- tax[eventos, on = "skill", nomatch = 0L]

panel_maestro <- readRDS(file.path(dir_interim, "panel_maestro_curricular_2000_2017.rds"))
base_grid <- unique(panel_maestro[, .(unitid, fos, year, is_r1, prestige_tier_num, field_status_index)],
                     by = c("unitid", "fos", "year"))
rm(panel_maestro); gc()

eventos <- merge(eventos, base_grid, by = c("unitid", "fos", "year"), all.x = TRUE)

message("[2/4] Gradiente por NIVEL DE PRESTIGIO INSTITUCIONAL x tipo de skill...")

tasa_adopcion_prestigio <- eventos[has_skill_lag == 0L, .(
  tasa_adopcion = mean(adopta_evento), n = .N
), by = .(clase, prestige_tier_num)]

tasa_abandono_prestigio <- eventos[has_skill_lag == 1L, .(
  tasa_abandono = mean(abandona_evento), n = .N
), by = .(clase, prestige_tier_num)]

setorder(tasa_adopcion_prestigio, clase, prestige_tier_num)
setorder(tasa_abandono_prestigio, clase, prestige_tier_num)

message("  Tasa de ADOPCION por tipo de skill x nivel de prestigio (0=no-doctoral,3=R1-elite):")
print(tasa_adopcion_prestigio)
message("  Tasa de ABANDONO por tipo de skill x nivel de prestigio:")
print(tasa_abandono_prestigio)

message("[3/4] Gradiente por ESTATUS DISCIPLINAR (terciles de field_status_index) x tipo de skill...")

eventos[, disciplina_tercil := cut(field_status_index, breaks = quantile(field_status_index, c(0, 1/3, 2/3, 1), na.rm = TRUE),
                                    labels = c("Baja concentracion elite", "Media", "Alta concentracion elite"), include.lowest = TRUE)]

tasa_adopcion_disciplina <- eventos[has_skill_lag == 0L & !is.na(disciplina_tercil), .(
  tasa_adopcion = mean(adopta_evento), n = .N
), by = .(clase, disciplina_tercil)]

tasa_abandono_disciplina <- eventos[has_skill_lag == 1L & !is.na(disciplina_tercil), .(
  tasa_abandono = mean(abandona_evento), n = .N
), by = .(clase, disciplina_tercil)]

setorder(tasa_adopcion_disciplina, clase, disciplina_tercil)
setorder(tasa_abandono_disciplina, clase, disciplina_tercil)

message("  Tasa de ADOPCION por tipo de skill x concentracion elite de la disciplina:")
print(tasa_adopcion_disciplina)
message("  Tasa de ABANDONO por tipo de skill x concentracion elite de la disciplina:")
print(tasa_abandono_disciplina)

message("[4/4] Guardando resultados descriptivos...")
dir.create("outputs/tables", showWarnings = FALSE, recursive = TRUE)
fwrite(tasa_adopcion_prestigio, "outputs/tables/descriptivo_adopcion_x_prestigio.csv")
fwrite(tasa_abandono_prestigio, "outputs/tables/descriptivo_abandono_x_prestigio.csv")
fwrite(tasa_adopcion_disciplina, "outputs/tables/descriptivo_adopcion_x_disciplina.csv")
fwrite(tasa_abandono_disciplina, "outputs/tables/descriptivo_abandono_x_disciplina.csv")

message("Listo.")
