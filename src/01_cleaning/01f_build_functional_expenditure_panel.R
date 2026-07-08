# ==============================================================================
# SCRIPT: 01f_build_functional_expenditure_panel.R
# OBJETIVO: Extraer TODAS las categorias de gasto funcional (no solo
#           Instruccion) de los archivos F1A (publicas, GASB) ya descargados
#           en 01e, para identificar POR QUE VIA especifica se ajustan las
#           instituciones mas dependientes de fondos estatales tras la
#           recesion -- ya que el gasto en instruccion (F1C011) no mostro
#           una caida significativa (ver 06h).
#
# Categorias extraidas (todas "Current year total"):
#   F1C011 Instruccion | F1C021 Investigacion | F1C031 Servicio publico |
#   F1C051 Apoyo academico | F1C061 Servicios estudiantiles |
#   F1C071 Apoyo institucional (administracion general) |
#   F1C081 Operacion y mantenimiento de planta |
#   F1C101 Becas y ayudas | F1C111 Empresas auxiliares |
#   F1C191 Gasto total
#
# Hipotesis a testear: Apoyo academico (F1C051, que tipicamente incluye
# decanatos, comites curriculares, administracion academica -- la capacidad
# organizacional de REVISAR y actualizar curricula) y Apoyo institucional
# (F1C071, administracion general) son canales mas plausibles que
# Instruccion pura (mayormente sueldos docentes, tipicamente protegidos)
# para un mecanismo de "menor capacidad de innovar curricularmente".
#
# AUTOR: Roberto Cantillan Carrasco
# FECHA: Julio 2026
# ==============================================================================

library(data.table)

dir_raw <- "data/raw/ipeds_finance"
dir_interim <- "data/interim"

vars_funcionales <- c(
  "F1C011", "F1C021", "F1C031", "F1C051", "F1C061",
  "F1C071", "F1C081", "F1C101", "F1C111", "F1C191"
)
nombres_funcionales <- c(
  F1C011 = "instruccion", F1C021 = "investigacion", F1C031 = "servicio_publico",
  F1C051 = "apoyo_academico", F1C061 = "servicios_estudiantiles",
  F1C071 = "apoyo_institucional", F1C081 = "operacion_mantenimiento",
  F1C101 = "becas_ayudas", F1C111 = "empresas_auxiliares", F1C191 = "gasto_total"
)

leer_funcional <- function(anio_a, anio_b, year_out) {
  yy <- sprintf("%02d%02d", anio_a, anio_b)
  zip_path <- file.path(dir_raw, sprintf("F%s_F1A.zip", yy))
  if (!file.exists(zip_path)) return(NULL)

  tmp_dir <- tempfile()
  dir.create(tmp_dir)
  archivos <- unzip(zip_path, exdir = tmp_dir)
  csv_path <- archivos[grepl("\\.csv$", archivos) & !grepl("_rv\\.csv$", archivos)]
  if (length(csv_path) == 0) csv_path <- archivos[grepl("\\.csv$", archivos)]
  csv_path <- csv_path[1]

  dt <- fread(csv_path)
  setnames(dt, toupper(names(dt)))

  cols_presentes <- intersect(c("UNITID", vars_funcionales), names(dt))
  out <- dt[, ..cols_presentes]
  # Rename explicito uno a uno (robusto a que falten columnas en algunos años)
  for (v in setdiff(cols_presentes, "UNITID")) setnames(out, v, nombres_funcionales[[v]])
  setnames(out, "UNITID", "unitid")
  out[, unitid := as.integer(unitid)]
  out[, year := year_out]
  out[]
}

message("[1/2] Leyendo gasto funcional por categoria, 2002-2017 (solo publicas F1A)...")
lista <- list()
for (a in 1:16) {
  b <- a + 1
  year_out <- 2000 + b
  res <- tryCatch(leer_funcional(a, b, year_out), error = function(e) {
    message(sprintf("  [aviso] fallo año %d: %s", year_out, conditionMessage(e))); NULL
  })
  if (!is.null(res)) lista[[as.character(year_out)]] <- res
  message(sprintf("  -> año %d listo", year_out))
}
funcional_panel <- rbindlist(lista, fill = TRUE)

message("[2/2] Guardando panel de gasto funcional...")
fwrite(funcional_panel, file.path(dir_interim, "ipeds_functional_expenditure_panel.csv"))
message(sprintf("Listo: %s filas guardadas.", format(nrow(funcional_panel), big.mark = ",")))
print(sapply(funcional_panel, function(x) sum(!is.na(x))))
