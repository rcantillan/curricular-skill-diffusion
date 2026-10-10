# Diagnostic association: does measured volatility covary with coverage within
# the same institution-field? No causal or measurement-error interpretation.
library(data.table)
library(fixest)
setDTthreads(2L)
path <- "outputs/pilot/program_transition_diagnostics.csv"
if (!file.exists(path)) stop("Ejecuta primero 02_transition_stability.py")
dt <- fread(path)
stopifnot(!anyDuplicated(dt, by = c("cell_id", "year")))
dt[, `:=`(log_n_previous = log(n_previous), log_n_current = log(n_current))]
outcomes <- c("adoption_rate", "abandonment_rate", "mean_abs_delta_rca",
              "mean_abs_delta_score", "profile_cosine_change")
result <- list()
for (floor in c(1L, 9L)) {
  sample <- dt[coverage_min >= floor]
  for (outcome in outcomes) {
    f <- as.formula(paste(outcome,
                         "~ log_n_previous + log_n_current | cell_id + year"))
    # Equal weight per institution-field transition; no pseudo replication
    # of 2,070 highly dependent skill observations.
    m <- feols(f, data = sample, cluster = ~unitid)
    tab <- as.data.table(coeftable(m), keep.rownames = "term")
    setnames(tab, c("term", "estimate", "se", "t", "p"))
    tab[, `:=`(outcome = outcome, min_coverage = floor, observations = nobs(m))]
    result[[paste(floor, outcome)]] <- tab
  }
}
table <- rbindlist(result)
fwrite(table, "outputs/pilot/within_program_coverage.csv")
report <- capture.output({
  cat("COBERTURA Y VOLATILIDAD DENTRO DEL MISMO PROGRAMA\n")
  cat("FE institution-field y año; SE agrupados por institución.\n")
  cat("Asociaciones diagnósticas: no efectos causales ni prueba de error de medición.\n\n")
  print(table)
})
writeLines(report, "outputs/pilot/within_program_coverage.txt")
cat(paste(report, collapse = "\n"), "\n")
