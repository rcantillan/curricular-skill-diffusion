# ==============================================================================
# SCRIPT: 01h_build_fte_enrollment_panel.R
# OBJETIVO: Construir panel institucion x año de matricula FTE total (Full-
#           Time Equivalent), usando el componente EFFY (Fall Enrollment,
#           FTE) de IPEDS, 2002-2017. Necesario para normalizar el gasto
#           funcional (01f/06i) por estudiante y cerrar la pregunta abierta
#           sobre el mecanismo de recursos.
#
# EFFYLEV==1 ("All students total") & LSTUDY==999 ("Generated total") da
# exactamente una fila por institucion con el FTE total (EFYTOTLT).
#
# COBERTURA: 2008-2017 unicamente. Los archivos 2002-2007 usan un formato
# distinto (desglose FYRACE01-24 por raza/genero, sin columna de "gran
# total" directa) -- no se proceso por alcance de tiempo. No afecta el
# diseño del mecanismo (compara pre/post 2009): 2008 sigue disponible como
# ancla pre-tratamiento inmediata.
#
# AUTOR: Roberto Cantillan Carrasco
# FECHA: Julio 2026
# ==============================================================================

library(data.table)

dir_raw <- "data/raw/ipeds_enrollment"
dir_interim <- "data/interim"

leer_effy <- function(anio) {
  zip_path <- file.path(dir_raw, sprintf("EFFY%d.zip", anio))
  if (!file.exists(zip_path)) return(NULL)

  tmp_dir <- tempfile()
  dir.create(tmp_dir)
  archivos <- unzip(zip_path, exdir = tmp_dir)
  csv_path <- archivos[grepl("\\.csv$", archivos) & !grepl("_rv\\.csv$", archivos)]
  if (length(csv_path) == 0) csv_path <- archivos[grepl("\\.csv$", archivos)]
  csv_path <- csv_path[1]

  dt <- fread(csv_path)
  setnames(dt, toupper(names(dt)))

  sub <- dt[EFFYLEV == 1 & LSTUDY == 999, .(unitid = as.integer(UNITID), fte_matricula = EFYTOTLT)]
  sub[, year := anio]
  unique(sub, by = "unitid")
}

message("[1/2] Leyendo matricula FTE 2008-2017...")
lista <- list()
for (anio in 2008:2017) {
  res <- tryCatch(leer_effy(anio), error = function(e) {
    message(sprintf("  [aviso] fallo año %d: %s", anio, conditionMessage(e))); NULL
  })
  if (!is.null(res)) {
    lista[[as.character(anio)]] <- res
    message(sprintf("  -> año %d: %d instituciones", anio, nrow(res)))
  }
}
fte_panel <- rbindlist(lista)

message("[2/2] Guardando panel de matricula FTE...")
fwrite(fte_panel, file.path(dir_interim, "ipeds_fte_enrollment_panel.csv"))
message(sprintf("Listo: %s filas guardadas.", format(nrow(fte_panel), big.mark = ",")))
