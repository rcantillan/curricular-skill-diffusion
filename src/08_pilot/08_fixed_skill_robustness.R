# Fixed-skill longitudinal diagnostic; estimates associations, not transmission.
# Run: Rscript src/08_pilot/08_fixed_skill_robustness.R fixed_seed1
library(data.table)
library(fixest)
setDTthreads(2L)
setFixest_nthreads(2L)
args <- commandArgs(trailingOnly=TRUE)
if (length(args)!=1L || !grepl("^[A-Za-z0-9_-]+$", args[1])) {
  stop("Indica el tag: Rscript src/08_pilot/08_fixed_skill_robustness.R fixed_seed1")
}
tag <- args[1]
folder <- file.path("data/derived/pilot", paste0("continuous_diffusion_",tag))
out <- file.path("outputs/pilot",tag)
if (!file.exists(file.path(folder,"complete.json"))) stop("El constructor no ha terminado.")
paths <- file.path(folder,paste0("continuous_",2008:2017,".csv.gz"))
if (!all(file.exists(paths))) stop("Faltan años del piloto.")
dt <- rbindlist(lapply(paths,fread))
stopifnot(!anyDuplicated(dt,by=c("cell_id","skill_id","year")))
skill_sets <- dt[,.(set=list(sort(unique(skill_id)))),by=year]$set
if (!all(vapply(skill_sets,function(x) identical(x,skill_sets[[1]]),logical(1)))) {
  stop("Se requieren las mismas DWAs en todos los años; usa --sampling fixed.")
}
dt[,`:=`(lag_score_z2=lag_score_z^2,log_n_previous=log(n_previous),
         log_n_current=log(n_current),log_n_same_inst=log1p(n_same_inst),
         log_n_other=log1p(n_other))]
needed <- c("delta_score_z","lag_score_z","rd","same_inst_score_z",
            "same_field_score_z","other_score_z")
valid <- Reduce(`&`,lapply(dt[,..needed],is.finite))
complete <- dt[valid]
scales <- list()
for (x in c("rd","same_inst_score_z","same_field_score_z","other_score_z")) {
  ref <- complete[coverage_min>=9,get(x)]
  avg <- mean(ref); deviation <- sd(ref)
  if (!is.finite(deviation) || deviation<=0) stop(paste("Sin variación:",x))
  complete[,(paste0(x,"_std")):=(get(x)-avg)/deviation]
  scales[[x]] <- data.table(variable=x,main_mean=avg,main_sd=deviation)
}
fwrite(rbindlist(scales),file.path(out,"robustness_predictor_scales.csv"))
controls <- paste("lag_score_z + lag_score_z2 + log_n_previous + log_n_current +",
                  "log_n_same_inst + log_n_other")
common_fe <- "| cell_id + skill_id^year + field_id^year"
skill_fe <- "| cell_id^skill_id + skill_id^year + field_id^year"
both <- "rd_std + same_inst_score_z_std + same_field_score_z_std"
forms <- list(
  program_fe_three_channels=as.formula(paste("delta_score_z ~",both,"+ other_score_z_std +",controls,common_fe)),
  program_skill_portfolio=as.formula(paste("delta_score_z ~ rd_std +",controls,skill_fe)),
  program_skill_inst_only=as.formula(paste("delta_score_z ~ rd_std + same_inst_score_z_std +",controls,skill_fe)),
  program_skill_field_only=as.formula(paste("delta_score_z ~ rd_std + same_field_score_z_std +",controls,skill_fe)),
  program_skill_two_channels=as.formula(paste("delta_score_z ~",both,"+",controls,skill_fe)),
  program_skill_three_channels=as.formula(paste("delta_score_z ~",both,"+ other_score_z_std +",controls,skill_fe)))
results <- list(); samples <- list(); diagnostics <- list(); fits <- list()
for (floor in c(9L,3L)) {
  sample <- complete[coverage_min>=floor]
  # Restrict ALL specifications to the same repeated program-skill pairs.
  repeated <- sample[,.N,by=.(cell_id,skill_id)][N>=2,.(cell_id,skill_id)]
  sample <- sample[repeated,on=.(cell_id,skill_id),nomatch=0L]
  if (!nrow(sample)) stop("Sin pares programa-skill repetidos.")
  samples[[as.character(floor)]] <- data.table(min_coverage=floor,rows=nrow(sample),
    institutions=uniqueN(sample$unitid),program_year_pairs=uniqueN(sample,by=c("cell_id","year")),
    program_skill_pairs=uniqueN(sample,by=c("cell_id","skill_id")),skills=uniqueN(sample$skill_id))
  # Channel correlation after the program-level FE used in the original pilot.
  vars <- c("rd_std","same_inst_score_z_std","same_field_score_z_std","other_score_z_std")
  residualized <- lapply(vars,function(v) {
    residuals(feols(as.formula(paste(v,"~ 1",common_fe)),data=sample,fixef.rm="none"))
  })
  correlations <- cor(do.call(cbind,residualized))
  dimnames(correlations) <- list(vars,vars)
  fwrite(as.data.table(correlations,keep.rownames="variable"),
         file.path(out,paste0("channel_correlations_coverage",floor,".csv")))
  for (name in names(forms)) {
    # Retain singleton observations: repeated-pair restriction already targets
    # program-skill identification and common samples must remain comparable.
    fit <- feols(forms[[name]],data=sample,cluster=~unitid,fixef.rm="none")
    tab <- as.data.table(coeftable(fit),keep.rownames="term")
    setnames(tab,c("term","estimate","se","t","p"))
    tab[,`:=`(model=name,min_coverage=floor,observations=nobs(fit))]
    results[[paste(floor,name)]] <- tab
    diagnostics[[paste(floor,name)]] <- data.table(min_coverage=floor,model=name,
       observations=nobs(fit),r2_within=as.numeric(fitstat(fit,"wr2")[[1]]),
       collinear_variables=paste(fit$collin.var,collapse=", "))
    fits[[paste(floor,name)]] <- fit
  }
}
table <- rbindlist(results)
fwrite(table,file.path(out,"robustness_coefficients.csv"))
fwrite(rbindlist(samples),file.path(out,"robustness_samples.csv"))
fwrite(rbindlist(diagnostics),file.path(out,"robustness_fit.csv"))
saveRDS(fits,file.path(folder,"robustness_models.rds"))
main <- table[grepl("_std$",term),.(min_coverage,model,term,estimate,se,p,observations)]
report <- capture.output({
  cat("ROBUSTEZ CON DWAs FIJAS -- asociaciones, no transmisión\n\n")
  cat("Cada modelo dentro del corte usa la misma muestra de programa-skill repetidos.\n")
  cat("program_skill controla cada programa × DWA; program_fe replica el FE original en esa misma muestra.\n")
  cat("Las dinámicas con score previo y panel corto pueden tener sesgo; el control adicional no identifica causalidad.\n\n")
  print(rbindlist(samples))
  print(main)
  cat("\nCORRELACIONES DE CANALES: revisar los CSV de correlación residualizada.\n")
  cat("Un coeficiente residual negativo no demuestra inhibición de difusión.\n")
  cat("Esta es una muestra fija de DWAs; aún requiere repetir con otras semillas.\n")
})
writeLines(report,file.path(out,"robustness_summary.txt"))
cat(paste(report,collapse="\n"),"\n")
