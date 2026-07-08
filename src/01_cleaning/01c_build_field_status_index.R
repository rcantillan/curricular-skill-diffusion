# ==============================================================================
# SCRIPT: 01c_build_field_status_index.R
# OBJETIVO: Construir una medida de ESTATUS A NIVEL DE DISCIPLINA (cip2-year),
#           que hasta ahora no existia en el pipeline. Todo el estatus estaba
#           definido solo a nivel institucion (is_r1 / prestige_tier de
#           01a), aplicado por igual a todos los campos de una universidad.
#
# LOGICA (analoga a un location quotient / RCA, coherente con el resto del
# proyecto):
#   share_r1_campo(cip2, year)   = graduados de ese campo en instituciones R1
#                                  / graduados totales de ese campo, ese anio
#   share_r1_sistema(year)       = graduados en instituciones R1 (todos los
#                                  campos) / graduados totales del sistema
#   field_status_index(cip2,year) = share_r1_campo / share_r1_sistema
#
# Interpretacion: indice > 1 -> el campo esta SOBRE-representado en
# instituciones de elite ese anio (campo de alto estatus, ej. Medicine,
# Engineering); indice < 1 -> el campo esta sub-representado en elite y
# concentrado en instituciones de acceso masivo (campo de bajo estatus,
# ej. Basic Skills). Es una medida continua y VARIA POR ANIO, a diferencia
# de is_r1 que es fijo por institucion.
#
# Fuente: graduados IPEDS (data/raw/ipeds_2digit_grads_2000_2017.csv) cruzados
# con el panel de prestigio Carnegie corregido (01a). No depende del
# crosswalk field_code del Atlas (01b), así que puede construirse en paralelo.
#
# AUTOR: Roberto Cantillan Carrasco
# FECHA: Julio 2026
# ==============================================================================

library(data.table)

dir_raw     <- "data/raw"
dir_interim <- "data/interim"

path_grads    <- file.path(dir_raw, "ipeds_2digit_grads_2000_2017.csv")
path_carnegie <- file.path(dir_interim, "carnegie_prestige_panel_2000_2017.csv")
output_path   <- file.path(dir_interim, "field_status_index.csv")

message("[1/4] Cargando graduados IPEDS y prestigio Carnegie...")
grads <- fread(path_grads)
setnames(grads, "UnitID", "unitid")
grads[, `:=`(unitid = as.integer(unitid), year = as.integer(year))]
grads[, cipcode := formatC(as.integer(cipcode), width = 2, flag = "0")]

carnegie <- fread(path_carnegie, select = c("unitid", "year", "is_r1", "prestige_tier_num"))
carnegie <- unique(carnegie, by = c("unitid", "year"))

message("[2/4] Uniendo graduados con is_r1 institucional...")
grads_prestigio <- carnegie[grads, on = .(unitid, year)]
grads_prestigio <- grads_prestigio[!is.na(is_r1)]
grads_prestigio[, graduates_cnt := as.numeric(graduates_cnt)]

message("[3/4] Calculando indice de estatus por campo-anio (location quotient)...")

# Denominador de sistema: participacion de graduados-R1 en el total, por anio
sistema_t <- grads_prestigio[, .(
  grads_r1_sistema    = sum(graduates_cnt * (is_r1 == 1L), na.rm = TRUE),
  grads_total_sistema = sum(graduates_cnt, na.rm = TRUE)
), by = year]
sistema_t[, share_r1_sistema := grads_r1_sistema / grads_total_sistema]

# Numerador: participacion de graduados-R1 en el total, por campo (cip2) y anio
campo_t <- grads_prestigio[, .(
  grads_r1_campo    = sum(graduates_cnt * (is_r1 == 1L), na.rm = TRUE),
  grads_total_campo = sum(graduates_cnt, na.rm = TRUE),
  tier_promedio     = mean(prestige_tier_num, na.rm = TRUE)  # gradiente continuo, no solo binario
), by = .(cipcode, year)]
campo_t[, share_r1_campo := grads_r1_campo / grads_total_campo]

field_status <- sistema_t[campo_t, on = "year"]
field_status[, field_status_index := share_r1_campo / share_r1_sistema]
setnames(field_status, "cipcode", "cip2")

field_status <- field_status[, .(cip2, year, grads_total_campo, share_r1_campo,
                                  share_r1_sistema, field_status_index, tier_promedio)]
setorder(field_status, cip2, year)

message("[4/4] Guardando indice de estatus disciplinar...")
fwrite(field_status, output_path)

message("\n--- RESUMEN ---")
message(sprintf("Filas (cip2 x year): %d", nrow(field_status)))
message("Top 5 campos con mayor field_status_index promedio (mas 'elite'):")
print(field_status[, .(status_promedio = mean(field_status_index, na.rm = TRUE)), by = cip2][order(-status_promedio)][1:5])
message("Top 5 campos con menor field_status_index promedio (mas 'acceso masivo'):")
print(field_status[, .(status_promedio = mean(field_status_index, na.rm = TRUE)), by = cip2][order(status_promedio)][1:5])
message(sprintf("Listo: %s", output_path))
