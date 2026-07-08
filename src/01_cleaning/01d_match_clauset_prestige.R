# ==============================================================================
# SCRIPT: 01d_match_clauset_prestige.R
# OBJETIVO: Incorporar el prestigio derivado de REDES DE CONTRATACION DOCENTE
#           (Clauset, Arbesman & Larremore 2015, Science Advances) como una
#           medida de estatus alternativa a la clasificacion administrativa
#           Carnegie -- disponible solo para Computer Science, Business e
#           History, las 3 disciplinas que ese estudio releva.
#
# La medida `pi` (prestigio via minimum-violations ranking sobre la red de
# quien-contrata-a-quien) es una medida de estatus genuinamente relacional,
# no administrativa como Carnegie -- permite verificar si los resultados
# nulos de las secciones anteriores se sostienen con una medida de "estatus"
# construida de forma totalmente distinta.
#
# MATCHING: los archivos de Clauset no traen UnitID de IPEDS, solo nombres
# de institucion en formato libre (ej. "UC Berkeley", "MIT"). Se hace match
# aproximado (stringdist, distancia Jaro-Winkler) contra los nombres
# institucionales de Carnegie, con normalizacion de texto (minusculas, sin
# puntuacion, sin palabras genericas). Se guarda el score de similitud para
# poder filtrar matches de baja confianza.
#
# AUTOR: Roberto Cantillan Carrasco
# FECHA: Julio 2026
# ==============================================================================

library(data.table)
library(stringdist)

dir_raw <- "data/raw/clauset_hiring_networks"
dir_interim <- "data/interim"

normalizar_nombre <- function(x) {
  x <- tolower(x)
  # Expandir abreviaturas comunes ANTES de quitar palabras genericas, porque
  # "UC Irvine" / "UCLA" no contienen "university" y quedan sin match contra
  # el nombre oficial IPEDS ("University of California-Irvine").
  x <- gsub("\\bucla\\b", "university of california los angeles", x)
  x <- gsub("\\buc ", "university of california ", x)
  x <- gsub("\\bst\\.? ", "saint ", x)
  x <- gsub("[^a-z0-9 ]", " ", x)
  x <- gsub("\\b(university|univ|college|the|of|at|campus|main|system)\\b", " ", x)
  x <- gsub("\\s+", " ", x)
  trimws(x)
}

message("[1/4] Cargando vertexlists de Clauset (CS, Business, History)...")
cs   <- fread(file.path(dir_raw, "cs_vertex.txt"))[, disciplina := "Computer Science"]
biz  <- fread(file.path(dir_raw, "biz_vertex.txt"))[, disciplina := "Business"]
hist <- fread(file.path(dir_raw, "hist_vertex.txt"))[, disciplina := "History"]
setnames(cs, 1:6, c("u_clauset", "pi", "USN2010", "NRC95", "region", "institution"))
setnames(biz, 1:6, c("u_clauset", "pi", "USN2010", "NRC95", "region", "institution"))
setnames(hist, 1:6, c("u_clauset", "pi", "USN2010", "NRC95", "region", "institution"))
clauset_all <- rbindlist(list(cs, biz, hist))
clauset_all[, nombre_norm := normalizar_nombre(institution)]

message(sprintf("  Instituciones Clauset (3 disciplinas): %d", nrow(clauset_all)))

message("[2/4] Cargando nombres institucionales de Carnegie (IPEDS)...")
carnegie <- fread(file.path(dir_interim, "carnegie_prestige_panel_2000_2017.csv"),
                   select = c("unitid", "institution_name"))
carnegie <- unique(carnegie[!is.na(institution_name)], by = "unitid")
carnegie[, nombre_norm := normalizar_nombre(institution_name)]

message("[3/4] Haciendo match aproximado (Jaro-Winkler)...")
dist_matrix <- stringdistmatrix(clauset_all$nombre_norm, carnegie$nombre_norm, method = "jw", p = 0.1)
mejor_match_idx <- apply(dist_matrix, 1, which.min)
mejor_match_dist <- apply(dist_matrix, 1, min)

clauset_all[, unitid := carnegie$unitid[mejor_match_idx]]
clauset_all[, institution_name_match := carnegie$institution_name[mejor_match_idx]]
clauset_all[, match_dist := mejor_match_dist]

# Umbral de confianza: distancia Jaro-Winkler < 0.10 (muy similar). Marcar
# matches dudosos para revision/exclusion en robustez.
clauset_all[, match_confiable := match_dist < 0.10]

message(sprintf("  Matches con distancia < 0.10 (confiables): %d de %d (%.1f%%)",
                sum(clauset_all$match_confiable), nrow(clauset_all),
                100 * mean(clauset_all$match_confiable)))

message("  Muestra de matches menos confiables (revisar manualmente si se usan):")
print(clauset_all[match_confiable == FALSE][order(-match_dist)][1:10,
      .(institution, institution_name_match, match_dist, disciplina)])

message("[4/4] Guardando crosswalk de prestigio Clauset...")
out <- clauset_all[match_confiable == TRUE, .(
  unitid, disciplina, prestigio_clauset = pi, usn2010_rank = USN2010,
  nrc95_rank = NRC95, region_clauset = region, institution_clauset = institution,
  match_dist
)]
fwrite(out, file.path(dir_interim, "clauset_prestige_crosswalk.csv"))

message(sprintf("\nListo: %d filas guardadas en data/interim/clauset_prestige_crosswalk.csv", nrow(out)))
message("Cobertura por disciplina:")
print(out[, .N, by = disciplina])
