# Lightweight audit only: no event-model estimation and no legacy overwrites.
# Run from the repository root. The public Atlas ID is an aggregated profile.
library(data.table)
setDTthreads(2L)
out <- "outputs/pilot"
dir.create(out, recursive = TRUE, showWarnings = FALSE)
dir.create("data/derived/pilot", recursive = TRUE, showWarnings = FALSE)
p <- readRDS("data/interim/panel_maestro_curricular_2000_2017.rds")
setDT(p)
stopifnot(all(c("id", "unitid", "fos", "year", "syllabi_cnt") %in% names(p)))
stopifnot(!anyDuplicated(p$id))
stopifnot(!anyDuplicated(p, by = c("unitid", "fos", "year")))
stopifnot(all(!is.na(p$syllabi_cnt)), all(p$syllabi_cnt >= 1))
c <- unique(p[, .(unitid, fos, year, syllabi_cnt, sector)])
setorder(c, unitid, fos, year)
c[, `:=`(year_previous = shift(year), coverage_previous = shift(syllabi_cnt)),
  by = .(unitid, fos)]
c[, year_gap := year - year_previous]
coverage <- rbindlist(lapply(c(1L, 3L, 5L, 9L), function(k) {
  all_pairs <- c[year_gap == 1L]
  annual <- all_pairs[syllabi_cnt >= k & coverage_previous >= k]
  data.table(min_syllabi_both_years = k,
    annual_profile_pairs = nrow(annual),
    fraction_of_annual_pairs = nrow(annual) / nrow(all_pairs),
    institutions = uniqueN(annual$unitid), fields = uniqueN(annual$fos))
}))
annual <- c[, .(profiles = .N, institutions = uniqueN(unitid),
  fields = uniqueN(fos), represented_syllabi = sum(syllabi_cnt),
  median_syllabi = as.numeric(median(syllabi_cnt)), fraction_single = mean(syllabi_cnt == 1),
  consecutive_pairs = sum(year_gap == 1L, na.rm = TRUE),
  gap_pairs = sum(year_gap > 1L, na.rm = TRUE)), by = year][order(year)]
by_sector <- c[, .(profiles = .N, institutions = uniqueN(unitid),
  median_syllabi = as.numeric(median(syllabi_cnt)), fraction_single = mean(syllabi_cnt == 1),
  fraction_gaps = mean(year_gap > 1L, na.rm = TRUE)), by = sector]
fwrite(coverage, file.path(out, "audit_coverage.csv"))
fwrite(annual, file.path(out, "audit_by_year.csv"))
fwrite(by_sector, file.path(out, "audit_by_sector.csv"))
fwrite(p, "data/derived/pilot/master_metadata.csv")
report <- capture.output({
  cat("AUDITORIA DEL PANEL -- sin reestimar modelos\n\n")
  cat("Unidad: perfil agregado institution-field-year, no syllabus individual\n")
  cat("Perfiles:", nrow(p), "\nInstituciones:", uniqueN(p$unitid),
      "\nFields:", uniqueN(p$fos), "\nSyllabi representados:", sum(p$syllabi_cnt), "\n")
  cat("Mediana de syllabi por perfil:", median(p$syllabi_cnt),
      "\nFraccion con uno:", mean(p$syllabi_cnt == 1),
      "\nFraccion con menos de diez:", mean(p$syllabi_cnt < 10), "\n")
  cat("Pares observados:", c[!is.na(year_gap), .N],
      "\nPares consecutivos:", c[year_gap == 1L, .N],
      "\nPares con gaps:", c[year_gap > 1L, .N],
      "\nFraccion con gaps:", c[!is.na(year_gap), mean(year_gap > 1L)], "\n\n")
  cat("COVERAGE EN AMBOS EXTREMOS DE LA TRANSICION\n")
  print(coverage)
  cat("\nCOBERTURA ANUAL\n")
  print(annual)
  cat("\nLos RDS de eventos y tablas anteriores siguen siendo resultados legacy.\n")
  cat("No se han regenerado ni deben confundirse con eventos anuales corregidos.\n")
})
writeLines(report, file.path(out, "audit_panel.txt"))
cat(paste(report, collapse = "\n"), "\n")
