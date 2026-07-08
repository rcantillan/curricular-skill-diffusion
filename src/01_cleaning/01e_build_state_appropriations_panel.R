# ==============================================================================
# SCRIPT: 01e_build_state_appropriations_panel.R
# OBJETIVO: Reemplazar el proxy binario publica/privada de 06g por la medida
#           REAL de dependencia de financiamiento estatal, usando el
#           componente de Finanzas de IPEDS (NCES) a nivel de institucion,
#           anios fiscales 2001-02 a 2016-17 (forms F1A para publicas GASB,
#           F2 para privadas sin fines de lucro FASB, F3 para privadas con
#           fines de lucro).
#
# Variables extraidas:
#   - Apropiaciones estatales: F1B11 (F1A) / F2D03 (F2) / F3D03 (F3, incluye
#     tambien apropiaciones locales -- limitacion, ver docs/replication_notes)
#   - Ingresos totales: F1D01 (F1A) / F2D16 (F2) / F3D09 (F3)
#   - Gasto en instruccion: F1C011 (F1A) -- medida DIRECTA de capacidad/
#     recursos institucionales, no solo de dependencia de financiamiento
#     (solo disponible para publicas en este ejercicio; F2/F3 usan otra
#     estructura de reporte de gastos funcionales que no se proceso en esta
#     ronda por alcance de tiempo).
#
# NOTA DE VINCULACION AÑO: se usa la convencion de que el archivo F<a><a+1>
# corresponde al anio fiscal que termina en 20(a+1), y se etiqueta como
# `year = 20(a+1)` en el panel -- consistente con el resto del proyecto
# (año = año de referencia/otoño). Cobertura: 2002-2017 (no se proceso
# 2000-2001 porque usan formularios pre-GASB/FASB con nombres de variable
# distintos, y el diseño no los necesita: el periodo pre-recesion de interes
# es 2005-2007).
#
# AUTOR: Roberto Cantillan Carrasco
# FECHA: Julio 2026
# ==============================================================================

library(data.table)

dir_raw <- "data/raw/ipeds_finance"
dir_interim <- "data/interim"

leer_finance <- function(anio_a, anio_b, tipo_form, year_out) {
  yy <- sprintf("%02d%02d", anio_a, anio_b)
  zip_path <- file.path(dir_raw, sprintf("F%s_%s.zip", yy, tipo_form))
  if (!file.exists(zip_path)) return(NULL)

  tmp_dir <- tempfile()
  dir.create(tmp_dir)
  archivos <- unzip(zip_path, exdir = tmp_dir)
  # Preferir el archivo SIN sufijo _rv (revisado), tomar el mas reciente/base
  csv_path <- archivos[grepl("\\.csv$", archivos) & !grepl("_rv\\.csv$", archivos)]
  if (length(csv_path) == 0) csv_path <- archivos[grepl("\\.csv$", archivos)]
  csv_path <- csv_path[1]

  dt <- fread(csv_path)
  setnames(dt, toupper(names(dt)))  # normalizar mayusculas (varia por año)

  if (tipo_form == "F1A") {
    cols <- c("UNITID", "F1B11", "F1D01", "F1C011")
    cols <- intersect(cols, names(dt))
    out <- dt[, ..cols]
    setnames(out, c("F1B11", "F1D01", "F1C011")[match(setdiff(cols, "UNITID"), c("F1B11","F1D01","F1C011"))],
             c("state_approp", "total_revenue", "gasto_instruccion")[match(setdiff(cols, "UNITID"), c("F1B11","F1D01","F1C011"))])
    if (!"gasto_instruccion" %in% names(out)) out[, gasto_instruccion := NA_real_]
  } else if (tipo_form == "F2") {
    cols <- intersect(c("UNITID", "F2D03", "F2D16"), names(dt))
    out <- dt[, ..cols]
    setnames(out, c("F2D03", "F2D16")[match(setdiff(cols, "UNITID"), c("F2D03","F2D16"))],
             c("state_approp", "total_revenue")[match(setdiff(cols, "UNITID"), c("F2D03","F2D16"))])
    out[, gasto_instruccion := NA_real_]
  } else if (tipo_form == "F3") {
    cols <- intersect(c("UNITID", "F3D03", "F3D09"), names(dt))
    out <- dt[, ..cols]
    setnames(out, c("F3D03", "F3D09")[match(setdiff(cols, "UNITID"), c("F3D03","F3D09"))],
             c("state_approp", "total_revenue")[match(setdiff(cols, "UNITID"), c("F3D03","F3D09"))])
    out[, gasto_instruccion := NA_real_]
  }
  out[, `:=`(unitid = as.integer(UNITID), year = year_out, form_type = tipo_form)]
  out[, UNITID := NULL]
  out[]
}

message("[1/3] Leyendo archivos de Finanzas IPEDS 2002-2017 (F1A/F2/F3)...")
lista <- list()
for (a in 1:16) {
  b <- a + 1
  year_out <- 2000 + b
  message(sprintf("  -> Año fiscal 20%02d-%02d (year=%d)", a, b, year_out))
  for (tipo in c("F1A", "F2", "F3")) {
    res <- tryCatch(leer_finance(a, b, tipo, year_out), error = function(e) NULL)
    if (!is.null(res)) lista[[paste(year_out, tipo)]] <- res
  }
}
finance_panel <- rbindlist(lista, fill = TRUE)

message(sprintf("[2/3] Total filas institucion-año-tipo: %s", format(nrow(finance_panel), big.mark = ",")))

finance_panel <- finance_panel[!is.na(state_approp) & !is.na(total_revenue) & total_revenue > 0]
finance_panel[, state_approp_share := state_approp / total_revenue]
# Recortar outliers imposibles (errores de reporte: share > 1 o < 0)
finance_panel <- finance_panel[state_approp_share >= 0 & state_approp_share <= 1]

message("[3/3] Guardando panel de apropiaciones estatales...")
fwrite(finance_panel, file.path(dir_interim, "ipeds_finance_state_approp_panel.csv"))

message(sprintf("Listo: %s filas guardadas.", format(nrow(finance_panel), big.mark = ",")))
message("Resumen state_approp_share por form_type:")
print(finance_panel[, .(n = .N, media = mean(state_approp_share), mediana = median(state_approp_share)), by = form_type])
