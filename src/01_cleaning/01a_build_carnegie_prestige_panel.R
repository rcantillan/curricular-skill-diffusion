# ==============================================================================
# SCRIPT: 01a_build_carnegie_prestige_panel.R
# OBJETIVO: Construir un panel longitudinal (2000-2017) de clasificacion
#           Carnegie por institucion, con una definicion de "R1" que es
#           consistente a traves de las distintas familias/vintages de
#           clasificacion Carnegie (2000, 2005, 2010, 2015, 2018, 2021...).
#
# CORRECCION CLAVE (respecto a 001.R):
#   La hoja CCData del archivo longitudinal reutiliza el mismo codigo VALUE
#   con significados distintos segun la familia de clasificacion (columna
#   `Group`). Por ejemplo, VALUE == 11 significa "Research Universities I"
#   dentro de Group == 1 (Doctoral), pero tambien "Special Focus Two-Year:
#   Technical Professions" dentro de Group == 6 (SF: 2Yr), y "Associate's--
#   Public 2-year colleges under 4-year universities" dentro de Group == 5
#   (Associates). Sin filtrar por Group, la regla original
#   `carnegie_code %in% c(11, 15)` clasificaba erroneamente como "elite R1"
#   a 285 filas institucion-anio (22% de todas las filas con VALUE en 11/15)
#   que en realidad son colleges de dos anios / enfoque tecnico especial.
#   Ver docs/replication_notes/carnegie_group_collision.md para el detalle
#   de la verificacion.
#
# AUTOR: Roberto Cantillan Carrasco
# FECHA: Junio 2026
# ==============================================================================

library(data.table)
library(readxl)

excel_path  <- "data/raw/Longitudinal-Public-Data-File-1973-2021.xlsx"
output_path <- "data/interim/carnegie_prestige_panel_2000_2017.csv"

message("[1/5] Leyendo la hoja CCData del archivo maestro Carnegie...")
carnegie_raw <- as.data.table(read_excel(excel_path, sheet = "CCData"))

# 1. Seleccionar columnas relevantes, incluyendo Group/GrpLabel:
#    Group es la clasificacion de "nivel" (Doctoral, Master's, Bachelor's,
#    Associates, SF:2Yr, etc.) armonizada a traves de vintages por el propio
#    archivo longitudinal del Carnegie Classification (CCIHE). VALUE solo es
#    interpretable de forma segura DENTRO de un mismo Group.
carnegie_clean <- carnegie_raw[, .(
  unitid          = as.integer(C_UNITID),
  year            = as.integer(YEAR),
  institution_name = INSTNM,
  carnegie_group    = as.integer(Group),
  carnegie_group_label = GrpLabel,
  carnegie_value    = as.integer(VALUE),
  carnegie_label    = CatLabel,
  control           = CONTROL
)]

carnegie_clean <- unique(carnegie_clean[!is.na(unitid)])

# 2. Grilla balanceada 2000-2017 y Rolling Join (LOCF) para llenar anios
#    intercensales sin clasificacion reportada ese anio exacto.
todos_los_id <- unique(carnegie_clean$unitid)
anios_panel  <- 2000:2017
panel_base   <- as.data.table(expand.grid(unitid = todos_los_id, year = anios_panel))

setorder(carnegie_clean, unitid, year)
setorder(panel_base, unitid, year)

message("[2/5] Generando panel longitudinal via Rolling Join (LOCF)...")
carnegie_final <- carnegie_clean[panel_base, on = .(unitid, year), roll = TRUE]
carnegie_final <- carnegie_final[year %in% anios_panel]

# 3. Definicion de is_r1 RESTRINGIDA al grupo Doctoral (Group == 1).
#    Dentro de ese grupo, el codigo del nivel de investigacion mas alto es:
#      - VALUE == 11 ("Research Universities I")      -> vintages <= 1994
#      - VALUE == 15 ("...Extensive"/"RU/VH"/"Highest/Very High Research")
#                                                        -> vintages >= 2000
#    Verificado empiricamente contra las 30 combinaciones (vintage, VALUE,
#    CatLabel) presentes en Group == 1 entre 1973 y 2021.
message("[3/6] Aplicando definicion de is_r1 restringida a Group == 1 (Doctoral)...")
carnegie_final[, is_doctoral := fifelse(!is.na(carnegie_group) & carnegie_group == 1L, 1L, 0L)]
carnegie_final[, is_r1 := fifelse(is_doctoral == 1L & carnegie_value %in% c(11L, 15L), 1L, 0L)]
# Nivel "R2" (VALUE 16) y "R3/DRU" (VALUE 17) quedan disponibles como gradiente
carnegie_final[, is_r2 := fifelse(is_doctoral == 1L & carnegie_value == 16L, 1L, 0L)]
carnegie_final[, is_r3 := fifelse(is_doctoral == 1L & carnegie_value == 17L, 1L, 0L)]

# 3b. GRADIENTE ORDINAL DE PRESTIGIO (en vez de is_r1 binario)
#     Colapsar a un binario R1/no-R1 descarta variacion real: una institucion
#     R2 (alta actividad investigativa, VALUE==16) y una Associate's college
#     (Group != 1) quedan ambas en "no-R1", pese a ser estructuralmente muy
#     distintas. prestige_tier_num da una escala ordinal 0-3 utilizable como
#     variable continua/ordinal en los modelos de 05_models/.
#       3 = R1 / Very High Research (elite)
#       2 = R2 / High Research
#       1 = R3, DRU u otro doctoral de investigacion moderada
#       0 = No-doctoral (Master's, Bachelor's, Associates, SF, etc.)
message("[4/6] Construyendo gradiente ordinal prestige_tier...")
carnegie_final[, prestige_tier_num := fifelse(
  is_doctoral == 1L,
  fifelse(carnegie_value %in% c(11L, 15L), 3L,
    fifelse(carnegie_value == 16L, 2L,
      fifelse(carnegie_value == 17L, 1L, 1L))),
  0L
)]
carnegie_final[, prestige_tier := factor(
  prestige_tier_num,
  levels = 0:3,
  labels = c("No-doctoral", "Doctoral-moderado", "R2-alto", "R1-elite")
)]

# 3c. FLAG DE TRANSICION "LIMPIA" DE NIVEL (para el event-study de
#     reclasificacion). Una transicion es "limpia" si, tras cambiar de
#     prestige_tier_num, la institucion se MANTIENE en el nuevo nivel (o
#     superior) el resto de la ventana del panel -- es decir, no es un
#     rebote de borde entre ciclos de clasificacion. Ejemplos verificados de
#     rebote (NO limpios): University of Arkansas (R1->R2->R1->R1),
#     University of Colorado Denver (R2->R1->R2->R2), George Washington
#     University (R1->R2->R1->R1). Ver docs/replication_notes/ para el
#     detalle.
message("[5/6] Marcando transiciones limpias de prestige_tier (sin reversion)...")
setorder(carnegie_final, unitid, year)
carnegie_final[, `:=`(
  tier_sube  = prestige_tier_num > shift(prestige_tier_num),
  tier_baja  = prestige_tier_num < shift(prestige_tier_num)
), by = unitid]

marcar_transiciones_limpias <- function(dt) {
  dt[, clean_promotion := FALSE]
  dt[, clean_demotion  := FALSE]
  for (uid in unique(dt$unitid)) {
    idx <- which(dt$unitid == uid)
    sub <- dt[idx]
    n <- nrow(sub)
    if (n < 2) next
    for (i in 2:n) {
      if (isTRUE(sub$tier_sube[i])) {
        nuevo_nivel <- sub$prestige_tier_num[i]
        # "Limpia" si de aqui al final del panel nunca vuelve a caer bajo ese nivel
        if (i == n || all(sub$prestige_tier_num[i:n] >= nuevo_nivel, na.rm = TRUE)) {
          dt[idx[i], clean_promotion := TRUE]
        }
      }
      if (isTRUE(sub$tier_baja[i])) {
        nuevo_nivel <- sub$prestige_tier_num[i]
        if (i == n || all(sub$prestige_tier_num[i:n] <= nuevo_nivel, na.rm = TRUE)) {
          dt[idx[i], clean_demotion := TRUE]
        }
      }
    }
  }
  dt
}
carnegie_final <- marcar_transiciones_limpias(carnegie_final)
carnegie_final[, c("tier_sube", "tier_baja") := NULL]

# 4. Limpiar codigos administrativos negativos (instituciones inactivas,
#    fusionadas, o que no existian ese anio: -1 a -6 en el esquema CCIHE)
carnegie_final <- carnegie_final[is.na(carnegie_value) | carnegie_value >= 0]

message("[6/6] Guardando panel...")
dir.create(dirname(output_path), showWarnings = FALSE, recursive = TRUE)
fwrite(carnegie_final, file = output_path, row.names = FALSE)

message("\n--- RESUMEN ---")
message(sprintf("  Filas totales: %s", format(nrow(carnegie_final), big.mark = ",")))
message(sprintf("  Filas is_r1==1: %s (%.2f%%)", format(sum(carnegie_final$is_r1), big.mark=","),
                100 * mean(carnegie_final$is_r1)))
message("  Distribucion de prestige_tier:")
print(carnegie_final[, .N, by = prestige_tier][order(-N)])
message(sprintf("  Instituciones-anio con promocion LIMPIA (sin reversion posterior): %d",
                sum(carnegie_final$clean_promotion, na.rm = TRUE)))
message(sprintf("  Instituciones-anio con degradacion LIMPIA (sin reversion posterior): %d",
                sum(carnegie_final$clean_demotion, na.rm = TRUE)))
message("Listo: data/interim/carnegie_prestige_panel_2000_2017.csv")
