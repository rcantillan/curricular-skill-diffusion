# ==============================================================================
# SCRIPT: 03e_skill_taxonomy.R
# OBJETIVO: Clasificar las DWA (Detailed Work Activities) en una taxonomia de
#           3 clases -- Socio-Cognitiva General, Socio-Cognitiva Especializada,
#           Fisico-Sensorial -- analoga a la de Alabdulkareem et al. (2018).
#
# CORRECCION METODOLOGICA (julio 2026): un primer intento replico su metodo
# exacto (red de co-especializacion entre skills + Louvain) pero aplicado a
# nuestras celdas INSTITUCION x DISCIPLINA en vez de OCUPACION x SKILL. El
# resultado NO separaba cognitivo de fisico -- ej. "Develop financial
# analysis methods" caia en el cluster "fisico", y "Give medications or
# immunizations" en el cluster "cognitivo". La razon: en nuestros datos, la
# co-ocurrencia de skills esta organizada por LOGICA CURRICULAR DISCIPLINAR
# (que skills se enseñan juntas en un mismo programa), no por la funcion
# cognitiva/fisica de la actividad -- un programa de Enfermeria enseña
# "dar medicamentos" y "monitorear signos vitales" juntos sin importar su
# dominio funcional. El Louvain sobre esa red recupera clusters
# disciplinares, no el eje cognitivo-fisico.
#
# FIX: en vez de inferir el dominio desde nuestros propios datos, se usa la
# jerarquia OFICIAL del Content Model de O*NET (externa, no inventada por
# nosotros). Cada DWA pertenece a una Generalized Work Activity (GWA, via
# Element ID), y las GWA se organizan en 4 ramas de primer nivel bajo "4.A
# Work Activities":
#   4.A.1 Information Input          (como se obtiene la informacion)
#   4.A.2 Mental Processes           (procesamiento, planificacion, decision)
#   4.A.3 Work Output                (actividades FISICAS, equipos, vehiculos)
#   4.A.4 Interacting With Others    (interaccion social/supervision)
# Definicion textual oficial de 4.A.3 (O*NET Content Model Reference): "What
# PHYSICAL activities are performed, what equipment and vehicles are
# operated/controlled..." -- esto es precisamente el dominio Fisico-Sensorial.
# 4.A.1+4.A.2+4.A.4 se agrupan como Socio-Cognitivo (el "socio" cubre la
# rama de interaccion social/supervision, 4.A.4).
#
# Fuente: DWA Reference.txt, base de datos publica O*NET 29.1
# (https://www.onetcenter.org/database.html). Match exacto con nuestras
# 2,070 skills: 2,067/2,070 (99.9%).
#
# La especificidad (General vs. Especializada) DENTRO del dominio
# Socio-Cognitivo se sigue calculando empiricamente desde nuestra propia
# matriz RCA (contribucion a la anidacion / nestedness, vectorizado), ya
# que esa pregunta -- que tan "nuclear" es una skill en la estructura
# curricular observada -- si es una pregunta legitima sobre nuestros datos,
# a diferencia de la clasificacion de dominio.
#
# AUTOR: Roberto Cantillan Carrasco
# FECHA: Julio 2026
# ==============================================================================

library(data.table)
library(Matrix)

dir_interim <- "data/interim"
dir_rca <- file.path(dir_interim, "rca_by_year")

message("[1/5] Cargando clasificacion oficial O*NET (DWA -> GWA -> dominio)...")
dwa_ref <- fread("data/raw/onet_reference/dwa_reference.txt", sep = "\t", header = TRUE, quote = "")
setnames(dwa_ref, c("element_id", "iwa_id", "dwa_id", "dwa_title"))
dwa_ref[, rama := substr(element_id, 1, 5)]  # ej "4.A.3"
dwa_ref[, dominio := fifelse(rama == "4.A.3", "Fisico-Sensorial", "Socio-Cognitivo")]
dwa_ref <- unique(dwa_ref[, .(skill = dwa_title, dominio, rama)], by = "skill")

message(sprintf("  Clasificacion oficial: %d Fisico-Sensorial | %d Socio-Cognitivo",
                sum(dwa_ref$dominio == "Fisico-Sensorial"), sum(dwa_ref$dominio == "Socio-Cognitivo")))

message("[2/5] Cargando matriz RCA base (2000-2001) para calcular especificidad...")
rca_base <- rbindlist(list(
  fread(file.path(dir_rca, "rca_2000.csv"), select = c("unitid", "fos", "skill", "has_skill_rca")),
  fread(file.path(dir_rca, "rca_2001.csv"), select = c("unitid", "fos", "skill", "has_skill_rca"))
))
rca_base[, celda := paste(unitid, fos, sep = "_")]
rca_base_agg <- rca_base[, .(has_skill_rca = as.integer(any(has_skill_rca == 1L))), by = .(celda, skill)]

n_celdas_total <- uniqueN(rca_base_agg$celda)
prevalencia <- rca_base_agg[, .(prev = sum(has_skill_rca) / n_celdas_total), by = skill]
skills_validas <- prevalencia[prev >= 0.01 & prev <= 0.99, skill]
rca_base_agg <- rca_base_agg[skill %in% skills_validas]

message("[3/5] Construyendo matriz dispersa celda x skill...")
rca_base_agg[, celda_id := .GRP, by = celda]
rca_base_agg[, skill_id := .GRP, by = skill]
mapa_celdas <- unique(rca_base_agg[, .(celda_id, celda)])
mapa_skills <- unique(rca_base_agg[, .(skill_id, skill)])

X <- sparseMatrix(i = rca_base_agg$celda_id, j = rca_base_agg$skill_id,
                   x = rca_base_agg$has_skill_rca, dims = c(nrow(mapa_celdas), nrow(mapa_skills)))
colnames(X) <- mapa_skills[order(skill_id), skill]

message("[4/5] Calculando contribucion a la anidacion (nestedness) dentro del dominio Socio-Cognitivo...")

skills_cog <- dwa_ref[dominio == "Socio-Cognitivo" & skill %in% colnames(X), skill]
Xcog <- as.matrix(X[, skills_cog, drop = FALSE])

prev <- Matrix::colSums(Xcog)
ord <- order(-prev)
Xcog <- Xcog[, ord, drop = FALSE]
prev <- prev[ord]
nsk <- ncol(Xcog)

co <- crossprod(Xcog)
overlap_frac <- sweep(co, 2, prev, "/")
overlap_frac[!is.finite(overlap_frac)] <- 0

valid_mask <- upper.tri(matrix(0, nsk, nsk)) & outer(prev, prev, ">")
masked <- overlap_frac * valid_mask

sum_total <- sum(masked)
n_total   <- sum(valid_mask)
nodf_full <- sum_total / n_total

contrib_fila <- rowSums(masked)
contrib_col  <- colSums(masked)
n_fila <- rowSums(valid_mask)
n_col  <- colSums(valid_mask)

total_con_k <- contrib_fila + contrib_col
n_con_k     <- n_fila + n_col
nodf_menos_k <- (sum_total - total_con_k) / pmax(1, n_total - n_con_k)
c_s_vec <- nodf_full - nodf_menos_k

contribuciones <- data.table(skill = colnames(Xcog), c_s = c_s_vec)
mediana_cs <- median(contribuciones$c_s, na.rm = TRUE)
contribuciones[, especificidad := fifelse(c_s >= mediana_cs, "General", "Especializada")]

message(sprintf("  NODF (dominio cognitivo, base 2000-2001): %.4f | mediana c_s: %.5f", nodf_full, mediana_cs))

message("[5/5] Ensamblando taxonomia final de 3 clases...")
taxonomia <- copy(dwa_ref[, .(skill, dominio, rama)])
taxonomia <- contribuciones[, .(skill, c_s, especificidad)][taxonomia, on = "skill"]
taxonomia[, clase := fifelse(dominio == "Fisico-Sensorial", "Fisico-Sensorial",
                       fifelse(especificidad == "General", "Socio-Cognitiva General",
                       fifelse(especificidad == "Especializada", "Socio-Cognitiva Especializada", NA_character_)))]
# Skills cognitivas sin dato RCA base (muy raras/muy comunes, filtradas antes)
# quedan sin c_s -- se etiquetan aparte para no perderlas silenciosamente
taxonomia[is.na(clase) & dominio == "Socio-Cognitivo", clase := "Socio-Cognitiva (sin c_s, prevalencia extrema)"]

fwrite(taxonomia, file.path(dir_interim, "skill_taxonomy.csv"))
message("\n--- RESUMEN TAXONOMIA FINAL ---")
print(taxonomia[, .N, by = clase][order(-N)])
message(sprintf("Listo: %s", file.path(dir_interim, "skill_taxonomy.csv")))
