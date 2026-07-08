# ==============================================================================
# SCRIPT: 01g_build_instructional_staff_panel.R
# OBJETIVO: Construir panel institucion x año de PLANTA DOCENTE total
#           (headcount de "instructional staff"), usando el componente
#           Employees by Assigned Position (EAP) de IPEDS, 2001-2017.
#
# DOS FORMATOS DISTINTOS (IPEDS rediseño su encuesta de RRHH en 2012):
#   2001-2011: variables FTPT/FUNCTCD/FSTAT.
#     Total planta docente = FTPT==3 (ambos tiempos) & FUNCTCD==23
#     ("All instruction") & FSTAT==0 (todos los status).
#   2012-2017: variables EAPCAT/OCCUPCAT/FACSTAT.
#     Total planta docente = OCCUPCAT==210 ("Instructional staff, total")
#     & FACSTAT==0 ("All staff").
# Verificado empiricamente que ambos filtros producen EXACTAMENTE una fila
# por institucion (sin necesidad de agregar).
#
# AUTOR: Roberto Cantillan Carrasco
# FECHA: Julio 2026
# ==============================================================================

library(data.table)

dir_raw <- "data/raw/ipeds_eap_staff"
dir_interim <- "data/interim"

leer_eap <- function(anio) {
  zip_path <- file.path(dir_raw, sprintf("EAP%d.zip", anio))
  if (!file.exists(zip_path)) return(NULL)

  tmp_dir <- tempfile()
  dir.create(tmp_dir)
  archivos <- unzip(zip_path, exdir = tmp_dir)
  csv_path <- archivos[grepl("\\.csv$", archivos) & !grepl("_rv\\.csv$", archivos)]
  if (length(csv_path) == 0) csv_path <- archivos[grepl("\\.csv$", archivos)]
  csv_path <- csv_path[1]

  dt <- fread(csv_path)
  setnames(dt, toupper(names(dt)))

  if ("FUNCTCD" %in% names(dt)) {
    # Formato antiguo (2001-2011)
    sub <- dt[FTPT == 3 & FUNCTCD == 23 & FSTAT == 0, .(unitid = UNITID, instructional_staff = EAPTOT)]
  } else if ("OCCUPCAT" %in% names(dt)) {
    # Formato nuevo (2012-2017)
    sub <- dt[OCCUPCAT == 210 & FACSTAT == 0, .(unitid = UNITID, instructional_staff = EAPTOT)]
  } else {
    return(NULL)
  }
  sub[, unitid := as.integer(unitid)]
  sub[, year := anio]
  unique(sub, by = "unitid")
}

message("[1/2] Leyendo planta docente 2001-2017...")
lista <- list()
for (anio in 2001:2017) {
  res <- tryCatch(leer_eap(anio), error = function(e) {
    message(sprintf("  [aviso] fallo año %d: %s", anio, conditionMessage(e))); NULL
  })
  if (!is.null(res)) {
    lista[[as.character(anio)]] <- res
    message(sprintf("  -> año %d: %d instituciones", anio, nrow(res)))
  }
}
staff_panel <- rbindlist(lista)

message("[2/2] Guardando panel de planta docente...")
fwrite(staff_panel, file.path(dir_interim, "ipeds_instructional_staff_panel.csv"))
message(sprintf("Listo: %s filas guardadas.", format(nrow(staff_panel), big.mark = ",")))
