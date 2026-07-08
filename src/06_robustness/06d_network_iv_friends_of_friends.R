# ==============================================================================
# SCRIPT: 06d_network_iv_friends_of_friends.R
# OBJETIVO: Construir el mecanismo 2 del README (difusion horizontal entre
#           pares) que quedaba pendiente, e instrumentar la exposicion de red
#           directa usando la estructura "amigos de amigos" (Bramoulle,
#           Djebbari & Fortin 2009) -- ataca directamente el "problema del
#           reflejo" de Manski: mi adopcion y la de mis pares directos pueden
#           correlacionarse por shocks compartidos (no solo por contagio), pero
#           si la red NO es transitiva, la actividad de mis "amigos de mis
#           amigos que NO son mis amigos directos" es un instrumento valido
#           para la exposicion directa (afecta mi adopcion solo a traves de
#           mis pares directos, no directamente).
#
# POR QUE NO SE USA "MISMO ESTADO" O "MISMO SISTEMA" (SYSID) COMO RED:
# ------------------------------------------------------------------------
# Ambas son relaciones de EQUIVALENCIA (transitivas por definicion: si A y B
# comparten sistema, y B y C comparten sistema, entonces A y C TAMBIEN
# comparten sistema). Una red de equivalencia no tiene "amigos de amigos que
# no son mis amigos" -- son siempre el mismo conjunto, y el instrumento
# colapsa (no hay variacion util). Se necesita una red con intransitividad
# genuina.
#
# RED CONSTRUIDA: k-vecinos-mas-cercanos (k=10) en un espacio de similitud
# estructural (log-matricula, control publico/privado, nivel Carnegie basal
# en el año 2000), dentro del mismo Group Carnegie amplio para mantener
# comparabilidad. Un grafo k-NN es genericamente NO transitivo (mi vecino
# mas cercano no tiene por que compartir los mismos k vecinos que yo), lo
# que habilita la identificacion.
#
# LIMITACION HONESTA: esto es una red de EQUIVALENCIA ESTRUCTURAL (Burt),
# no una red de contacto social o geografico real -- es un proxy razonable
# de "instituciones que compiten/se comparan entre si", pero no observamos
# lazos reales (comites curriculares compartidos, movilidad de facultad,
# convenios). El supuesto de exclusion (que la actividad de mis
# amigos-de-amigos no-directos no me afecta mas que via mis amigos directos)
# es mas fuerte en una red de contacto real que en una de similitud.
#
# AUTOR: Roberto Cantillan Carrasco
# FECHA: Julio 2026
# ==============================================================================

library(data.table)
library(readxl)
library(FNN)
library(fixest)

dir_interim <- "data/interim"

message("[1/7] Construyendo atributos institucionales basales (año 2000)...")
carnegie_raw <- as.data.table(read_excel(
  "data/raw/Longitudinal-Public-Data-File-1973-2021.xlsx", sheet = "CCData"))

base2000 <- carnegie_raw[YEAR == 2000, .(
  unitid = as.integer(C_UNITID), Group = as.integer(Group),
  HCTTOT = as.numeric(HCTTOT), CONTROL = as.integer(CONTROL)
)]
base2000 <- unique(base2000[!is.na(unitid) & !is.na(HCTTOT) & HCTTOT > 0], by = "unitid")
base2000[, log_matricula := log(HCTTOT)]

carnegie_panel <- fread(file.path(dir_interim, "carnegie_prestige_panel_2000_2017.csv"))
tier2000 <- unique(carnegie_panel[year == 2000, .(unitid, prestige_tier_num)], by = "unitid")
base2000 <- tier2000[base2000, on = "unitid"]
base2000 <- base2000[!is.na(prestige_tier_num)]

message(sprintf("  Instituciones con atributos basales completos: %d", nrow(base2000)))

message("[2/7] Construyendo red k-NN (k=10) por similitud estructural dentro de Group...")
K <- 10
lista_aristas <- list()

for (g in unique(base2000$Group)) {
  sub <- base2000[Group == g]
  if (nrow(sub) < K + 1) next
  # prestige_tier_num es constante (0) fuera de Group==1 (Doctoral) por
  # construccion -- no aporta varianza ahi, y scale() produce NaN al dividir
  # por sd=0. Se excluye esa columna cuando no varia dentro del grupo.
  vars_similitud <- c("log_matricula", "prestige_tier_num", "CONTROL")
  sds <- sapply(sub[, ..vars_similitud], sd, na.rm = TRUE)
  vars_validas <- names(sds)[sds > 0]
  X <- scale(sub[, ..vars_validas])
  knn_res <- get.knn(X, k = K)
  for (i in seq_len(nrow(sub))) {
    vecinos_idx <- knn_res$nn.index[i, ]
    lista_aristas[[length(lista_aristas) + 1]] <- data.table(
      unitid = sub$unitid[i],
      vecino = sub$unitid[vecinos_idx]
    )
  }
}
red_directa <- rbindlist(lista_aristas)
message(sprintf("  Aristas red directa (dirigida, k=%d): %s", K, format(nrow(red_directa), big.mark = ",")))

message("[3/7] Construyendo red de 2do grado (amigos de amigos, excluyendo amigos directos)...")
# Para cada institucion, sus "amigos de amigos" = vecinos de sus vecinos, MENOS
# sus propios vecinos directos y ella misma.
red_2do_grado <- merge(red_directa, red_directa, by.x = "vecino", by.y = "unitid",
                        allow.cartesian = TRUE, suffixes = c("_1", "_2"))
setnames(red_2do_grado, "vecino_2", "amigo_de_amigo")
red_2do_grado <- red_2do_grado[, .(unitid, amigo_de_amigo)]
red_2do_grado <- unique(red_2do_grado[amigo_de_amigo != unitid])

# Excluir los que YA son amigos directos
red_directa_set <- red_directa[, .(unitid, vecino)]
setnames(red_directa_set, "vecino", "amigo_de_amigo")
red_directa_set[, es_directo := TRUE]
red_2do_grado <- red_directa_set[red_2do_grado, on = c("unitid", "amigo_de_amigo")]
red_2do_grado <- red_2do_grado[is.na(es_directo)][, es_directo := NULL]

message(sprintf("  Aristas red de 2do grado (excluyendo directos): %s", format(nrow(red_2do_grado), big.mark = ",")))
n_sin_2do_grado <- length(setdiff(unique(red_directa$unitid), unique(red_2do_grado$unitid)))
message(sprintf("  Instituciones sin ningun amigo-de-amigo no-directo (red totalmente transitiva local): %d", n_sin_2do_grado))

message("[4/7] Reconstruyendo tasa de adopcion/abandono institucion x año (2001-2017)...")
metricas_frontera <- readRDS(file.path(dir_interim, "metricas_frontera_anual.rds"))
top_skills <- readRDS("data/interim/top_skills_baseline.rds")  # FIX: fijado solo con base 2000-2001

eventos <- readRDS(file.path(dir_interim, "adoption_abandonment_events.rds"))
eventos_top <- eventos[skill %in% top_skills & !es_primer_anio_observado]
rm(eventos); gc()

panel_inst_year <- eventos_top[, .(
  tasa_adopcion = mean(adopta_evento[has_skill_lag == 0L]),
  tasa_abandono = mean(abandona_evento[has_skill_lag == 1L])
), by = .(unitid, year)]
rm(eventos_top); gc()

message("[5/7] Calculando exposicion directa (amigos) y de 2do grado (instrumento), rezagadas t-1...")

calc_exposicion <- function(red_dt, col_vecino) {
  m <- merge(red_dt, panel_inst_year, by.x = col_vecino, by.y = "unitid",
             allow.cartesian = TRUE)
  m[, .(exp_adopcion = mean(tasa_adopcion, na.rm = TRUE),
        exp_abandono = mean(tasa_abandono, na.rm = TRUE)), by = .(unitid, year)]
}

exp_directa   <- calc_exposicion(red_directa, "vecino")
exp_2do_grado <- calc_exposicion(red_2do_grado, "amigo_de_amigo")

setnames(exp_directa, c("exp_adopcion", "exp_abandono"), c("exp_directa_adopcion", "exp_directa_abandono"))
setnames(exp_2do_grado, c("exp_adopcion", "exp_abandono"), c("exp_2do_adopcion", "exp_2do_abandono"))

exp_directa[, year := year + 1L]    # t -> t+1: exposicion de t predice outcome de t+1
exp_2do_grado[, year := year + 1L]

message("[6/7] Ensamblando panel para 2SLS...")
panel_iv <- panel_inst_year[exp_directa, on = c("unitid", "year")]
panel_iv <- exp_2do_grado[panel_iv, on = c("unitid", "year")]
panel_iv <- panel_iv[!is.na(exp_directa_adopcion) & !is.na(exp_2do_adopcion)]
message(sprintf("  Panel final (institucion x año) para 2SLS: %d filas, %d instituciones",
                nrow(panel_iv), uniqueN(panel_iv$unitid)))

message("[7/7] Estimando 2SLS (fixest): exposicion directa instrumentada por 2do grado...")

modelo_iv_adopcion <- feols(
  tasa_adopcion ~ 1 | unitid + year | exp_directa_adopcion ~ exp_2do_adopcion,
  data = panel_iv, cluster = ~unitid
)
modelo_iv_abandono <- feols(
  tasa_abandono ~ 1 | unitid + year | exp_directa_abandono ~ exp_2do_abandono,
  data = panel_iv, cluster = ~unitid
)

message("\n--- 2SLS: EXPOSICION DIRECTA -> ADOPCION (instrumentada por amigos-de-amigos) ---")
print(summary(modelo_iv_adopcion))
message("\n--- Diagnostico de instrumento debil (adopcion) ---")
print(fitstat(modelo_iv_adopcion, "ivwald"))

message("\n--- 2SLS: EXPOSICION DIRECTA -> ABANDONO (instrumentada por amigos-de-amigos) ---")
print(summary(modelo_iv_abandono))
message("\n--- Diagnostico de instrumento debil (abandono) ---")
print(fitstat(modelo_iv_abandono, "ivwald"))

dir.create("outputs/tables", showWarnings = FALSE, recursive = TRUE)
etable(modelo_iv_adopcion, modelo_iv_abandono,
       headers = list("Adopcion", "Abandono"),
       file = "outputs/tables/tabla_network_iv.tex",
       title = "2SLS: exposicion de red directa (instrumentada por amigos-de-amigos de 2do grado)")

saveRDS(panel_iv, file.path(dir_interim, "panel_network_iv.rds"))
message("\nListo: outputs/tables/tabla_network_iv.tex y data/interim/panel_network_iv.rds")
