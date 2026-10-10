# Exploratory associations in inferred score change, not adoption or causality.
# User executes after 06_build_continuous_diffusion.py completes successfully.
library(data.table)
library(fixest)
setDTthreads(2L)
setFixest_nthreads(2L)
folder <- "data/derived/pilot/continuous_diffusion"
if (!file.exists(file.path(folder, "complete.json"))) {
  stop("Ejecuta primero 06_build_continuous_diffusion.py hasta que termine.")
}
paths <- file.path(folder, paste0("continuous_", 2008:2017, ".csv.gz"))
if (!all(file.exists(paths))) stop("Faltan archivos anuales del piloto.")
dt <- rbindlist(lapply(paths, fread))
stopifnot(!anyDuplicated(dt, by = c("cell_id", "year", "skill_id")))
dt[, `:=`(lag_score_z2 = lag_score_z^2,
          log_n_previous = log(n_previous), log_n_current = log(n_current),
          log_n_same_inst = log1p(n_same_inst),
          log_n_same_field = log1p(n_same_field), log_n_other = log1p(n_other))]
needed <- c("delta_score_z", "lag_score_z", "rd", "same_inst_score_z",
            "same_field_score_z", "other_score_z")
valid_rows <- Reduce(`&`, lapply(dt[, ..needed], is.finite))
complete <- dt[valid_rows]
# Standardize channel means on the same main complete sample, once, then
# keep the same scale for the >=3 sensitivity. Effects are per observed SD
# of a channel, not comparable causal effects of organizations/disciplines.
scales <- list()
for (x in c("rd", "same_inst_score_z", "same_field_score_z", "other_score_z")) {
  ref <- complete[coverage_min >= 9, get(x)]
  avg <- mean(ref); deviation <- sd(ref)
  if (!is.finite(deviation) || deviation <= 0) stop(paste("Sin variación:", x))
  complete[, (paste0(x, "_std")) := (get(x) - avg) / deviation]
  scales[[x]] <- data.table(variable=x, main_mean=avg, main_sd=deviation)
}
fwrite(rbindlist(scales), "outputs/pilot/continuous_predictor_scales.csv")
controls <- paste("lag_score_z + lag_score_z2 + log_n_previous + log_n_current +",
                  "log_n_same_inst + log_n_other")
effects <- "| cell_id + skill_id^year + field_id^year"
formulas <- list(
  baseline = as.formula(paste("delta_score_z ~", controls, effects)),
  portfolio = as.formula(paste("delta_score_z ~ rd_std +", controls, effects)),
  joint_channels = as.formula(paste("delta_score_z ~ rd_std + same_inst_score_z_std +",
    "same_field_score_z_std + other_score_z_std +", controls, effects)))
rows <- list(); design <- list(); models <- list()
for (floor in c(9L, 3L)) {
  sample <- complete[coverage_min >= floor]
  if (!nrow(sample)) stop("Muestra completa vacía.")
  design[[as.character(floor)]] <- data.table(
    min_coverage=floor, skill_rows=nrow(sample), institutions=uniqueN(sample$unitid),
    program_year_pairs=uniqueN(sample, by=c("cell_id", "year")),
    fields=uniqueN(sample$field_id), distinct_sampled_skills=uniqueN(sample$skill_id))
  for (name in names(formulas)) {
    m <- feols(formulas[[name]], data=sample, cluster=~unitid)
    tab <- as.data.table(coeftable(m), keep.rownames="term")
    setnames(tab, c("term", "estimate", "se", "t", "p"))
    tab[, `:=`(model=name, min_coverage=floor, observations=nobs(m))]
    rows[[paste(floor,name)]] <- tab
    models[[paste(floor,name)]] <- m
  }
}
table <- rbindlist(rows)
fwrite(table, "outputs/pilot/continuous_model_coefficients.csv")
fwrite(rbindlist(design), "outputs/pilot/continuous_model_sample.csv")
saveRDS(models, "data/derived/pilot/continuous_diffusion/models.rds")
main <- table[grepl("_std$", term), .(min_coverage,model,term,estimate,se,p,observations)]
report <- capture.output({
  cat("PILOTO DE CAMBIO CONTINUO -- asociaciones, no transmisión causal\n\n")
  cat("Outcome: cambio anual de score inferido, en SD de baseline de cada DWA.\n")
  cat("Muestra principal: >=9 syllabi en ambos años; sensibilidad: >=3.\n")
  cat("FE programa, skill×año y field×año; SE agrupados por institución.\n")
  cat("Control del score previo (lineal/cuadrático), cobertura y cantidad de sources.\n")
  cat("La cobertura actual es un ajuste de observación; podría ser endógena.\n")
  cat("Las tres especificaciones usan la misma muestra completa dentro de cada corte.\n\n")
  print(rbindlist(design))
  cat("\nPREDICTORES DEL REPERTORIO Y CANALES\n")
  print(main)
  cat("\nUn coeficiente positivo de RD sería compatible con búsqueda local, no prueba de difusión.\n")
  cat("Los canales representan scores de sources observados; homofilia y shocks comunes pueden explicar asociaciones.\n")
  cat("64 DWAs aleatorias por año: piloto computacional, pendiente replicar muestreo y ampliar universo de modelos.\n")
})
writeLines(report, "outputs/pilot/continuous_models.txt")
cat(paste(report, collapse="\n"), "\n")
