# ==============================================================================
# SCRIPT: 02_build_master_panel.R
# OBJETIVO: Unificar Carnegie (prestigio), IPEDS (graduados) y el Atlas
#           Curricular en un panel institucion x campo (CIP-2) x anio.
#
# CORRECCIONES CLAVE (respecto a 02_panel_construction.R original)
# ------------------------------------------------------------------
# 1. El merge Atlas <-> IPEDS ya NO se hace solo por (unitid, year). Se
#    incorpora la llave `cip2` construida en 01b_build_field_cip_crosswalk.py
#    para unir cada syllabus (con su field_name/field_code del Atlas) con la
#    fila de graduados IPEDS de la MISMA familia CIP de 2 digitos, evitando
#    el producto cartesiano que mezclaba campos no relacionados (p.ej. un
#    syllabus de "Medicine" con graduados de "Agriculture").
# 2. Se usa el panel de Carnegie corregido (carnegie_prestige_panel_2000_2017
#    .csv, generado por 01a) que ya trae `is_r1` bien definido dentro de
#    Group == 1 (Doctoral).
# 3. Se detecta explicitamente el escenario de field_code ambiguo (>1 familia
#    CIP de 2 digitos, 4 de las 62 categorias del Atlas) y se deja la
#    variable `fos_cip_ambiguous` disponible para excluir esas filas en
#    chequeos de robustez.
# 4. VARIABLES DE ESTATUS (julio 2026): se agregan dos medidas de estatus
#    que antes no existian.
#      - `prestige_tier_num`/`prestige_tier`: gradiente ordinal institucional
#        (0=no-doctoral, 1=doctoral moderado, 2=R2, 3=R1-elite), ya viene
#        incluido en el panel de 01a y se propaga automaticamente via el
#        merge de Carnegie.
#      - `field_status_index`: estatus A NIVEL DE DISCIPLINA (cip2 x year),
#        construido en 01c como location quotient de la concentracion de
#        graduados de ese campo en instituciones R1 relativo al sistema.
#        Antes, is_r1 se aplicaba por igual a TODAS las disciplinas de una
#        institucion; esta variable permite distinguir, p.ej., un programa
#        de Ingenieria (campo estructuralmente elite) de un programa de
#        Basic Skills (campo estructuralmente de acceso masivo) dentro de
#        la MISMA institucion.
#
# AUTOR: Roberto Cantillan Carrasco
# FECHA: Julio 2026
# ==============================================================================

library(data.table)

setDTthreads(threads = max(1L, parallel::detectCores() - 2L))
message(paste("Utilizando", getDTthreads(), "hilos para procesamiento multinucleo."))

dir_interim <- "data/interim"
dir_raw     <- "data/raw"

path_carnegie    <- file.path(dir_interim, "carnegie_prestige_panel_2000_2017.csv")
path_grads       <- file.path(dir_raw, "ipeds_2digit_grads_2000_2017.csv")
path_skills      <- file.path(dir_raw, "institution_fos_year.gzip")
path_crosswalk   <- file.path(dir_interim, "field_cip_crosswalk.csv")
path_field_status <- file.path(dir_interim, "field_status_index.csv")

output_panel <- file.path(dir_interim, "panel_maestro_curricular_2000_2017.rds")

estandarizar_llaves <- function(dt, nombre_dt) {
  cols <- names(dt)
  col_id <- grep("^unitid$|^c_unitid$", cols, ignore.case = TRUE, value = TRUE)[1]
  if (!is.na(col_id) && col_id != "unitid") setnames(dt, col_id, "unitid")
  col_yr <- grep("^year$|^ano$|^yr$", cols, ignore.case = TRUE, value = TRUE)[1]
  if (!is.na(col_yr) && col_yr != "year") setnames(dt, col_yr, "year")
  dt[, `:=`(unitid = as.integer(unitid), year = as.integer(year))]
  message(paste("-> Llaves estandarizadas para:", nombre_dt))
  return(dt)
}

# ==============================================================================
# PASO A: PRESTIGIO INSTITUCIONAL (Carnegie corregido, ya trae is_r1 correcto)
# ==============================================================================
message("\n[1/5] Cargando panel de prestigio Carnegie (corregido)...")
carnegie <- fread(path_carnegie)
carnegie <- estandarizar_llaves(carnegie, "Carnegie")
carnegie <- unique(carnegie, by = c("unitid", "year"))
setkey(carnegie, unitid, year)

# ==============================================================================
# PASO B: ATLAS CURRICULAR + CROSSWALK CIP-2
# ==============================================================================
message("\n[2/5] Cargando Atlas Curricular y aplicando crosswalk field_code -> cip2...")
skills_dt <- fread(path_skills)
skills_dt <- estandarizar_llaves(skills_dt, "Atlas Curricular")

crosswalk <- fread(path_crosswalk, colClasses = c(cip2 = "character"))
skills_dt <- merge(skills_dt, crosswalk[, .(field_name, field_code, cip2, is_ambiguous)],
                    by = c("field_name", "field_code"), all.x = TRUE)
setnames(skills_dt, c("field_name", "cip2", "is_ambiguous"), c("fos", "cipcode", "fos_cip_ambiguous"))

n_sin_cip <- skills_dt[is.na(cipcode), .N]
if (n_sin_cip > 0) {
  message(sprintf("  Aviso: %s filas de syllabi sin cip2 asignado (se excluyen del merge con graduados).", format(n_sin_cip, big.mark=",")))
}

skills_dt <- skills_dt[year %in% 2000:2017]
skills_dt[, id := as.character(id)]

# ==============================================================================
# PASO C: GRADUADOS IPEDS (cipcode de 2 digitos)
# ==============================================================================
message("\n[3/5] Cargando graduados IPEDS...")
grads <- fread(path_grads)
setnames(grads, "UnitID", "unitid")
grads <- estandarizar_llaves(grads, "Graduados IPEDS")
grads[, cipcode := formatC(as.integer(cipcode), width = 2, flag = "0")]

# ==============================================================================
# PASO D: EL GRAN MERGE, AHORA POR (unitid, year, cipcode)
# ==============================================================================
message("\n[4/6] Ejecutando el cruce maestro (unitid, year, cipcode)...")

panel_inst <- carnegie[grads, on = .(unitid, year), nomatch = 0L]
panel_inst <- panel_inst[is.na(carnegie_value) | carnegie_value >= 0]

setkey(panel_inst, unitid, year, cipcode)
setkey(skills_dt, unitid, year, cipcode)

panel_maestro <- skills_dt[panel_inst, on = .(unitid, year, cipcode), nomatch = 0L, allow.cartesian = TRUE]

rm(skills_dt, carnegie, grads, panel_inst)
gc()

# ==============================================================================
# PASO E: ESTATUS DISCIPLINAR (field_status_index de 01c)
# ==============================================================================
message("\n[5/6] Uniendo indice de estatus disciplinar (cip2 x year)...")
field_status <- fread(path_field_status, colClasses = c(cip2 = "character"))
field_status <- field_status[, .(cipcode = cip2, year, field_status_index, tier_promedio_campo = tier_promedio)]

panel_maestro <- field_status[panel_maestro, on = .(cipcode, year)]

n_sin_status <- panel_maestro[is.na(field_status_index), .N]
if (n_sin_status > 0) {
  message(sprintf("  Aviso: %s filas sin field_status_index (campo-anio sin graduados IPEDS registrados).",
                   format(n_sin_status, big.mark = ",")))
}

setorderv(panel_maestro, c("unitid", "cipcode", "year"))

message("\n--- RESUMEN FINAL ---")
message(paste("Total de observaciones:", format(nrow(panel_maestro), big.mark = ",")))
message(paste("Instituciones unicas:", format(uniqueN(panel_maestro$unitid), big.mark = ",")))
message(paste("Campos (cip2) unicos:", format(uniqueN(panel_maestro$cipcode), big.mark = ",")))
message(paste("Filas con crosswalk ambiguo (fos_cip_ambiguous==TRUE):",
              format(sum(panel_maestro$fos_cip_ambiguous, na.rm = TRUE), big.mark = ",")))
message("Distribucion de prestige_tier (institucional):")
print(panel_maestro[, .N, by = prestige_tier][order(-N)])
message(sprintf("field_status_index: media=%.2f, min=%.2f, max=%.2f",
                mean(panel_maestro$field_status_index, na.rm = TRUE),
                min(panel_maestro$field_status_index, na.rm = TRUE),
                max(panel_maestro$field_status_index, na.rm = TRUE)))
message("------------------------------------------")

message("\n[6/6] Guardando panel maestro (.rds)...")
saveRDS(panel_maestro, file = output_panel, compress = "gzip")
message(paste("Listo. Archivo guardado en:", output_panel))
