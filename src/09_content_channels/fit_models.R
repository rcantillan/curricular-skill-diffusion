# Continuous content channels. No RCA, skill-presence claims, or causal effects.
suppressPackageStartupMessages({library(data.table); library(fixest)})
setDTthreads(2L)
setFixest_nthreads(2L)
args <- commandArgs(trailingOnly=TRUE)
if (length(args)!=1L || !grepl('^[A-Za-z0-9_-]+$', args[1])) stop('Supply one output tag')
tag <- args[1]
folder <- file.path('data/derived/content_channels', tag)
out <- file.path('outputs/content_channels', tag)
unlink(file.path(out,'models_complete.txt'))
unlink(file.path(out,'skipped_or_failed_models.csv'))
if (!file.exists(file.path(folder,'complete.json'))) stop('Panel build has not finished')
dt <- rbindlist(lapply(file.path(folder, paste0('panel_',2008:2017,'.csv.gz')), fread))
stopifnot(!anyDuplicated(dt, by=c('cell_id','skill_id','year')))
dt[, `:=`(lag_score2=lag_score^2, log_n_previous=log(n_previous),
          log_n_current=log(n_current), log_n_inst=log1p(n_inst),
          log_n_field=log1p(n_field), time=year-2007)]
dt[, pair_id := .GRP, by=.(cell_id,skill_id)]
channel_variables <- c('same_inst','same_field','hiring2015','hiring2022')
scale_rows <- list()
for (v in channel_variables) {
  train_end <- if (v=='hiring2015') 2015L else 2013L
  ref <- dt[year<=train_end & coverage1>=9 & is.finite(get(v)), get(v)]
  center <- mean(ref); spread <- sd(ref)
  # Entirely missing / constant hiring variables are not silently imputed.
  dt[, (paste0(v,'_std')) := if (is.finite(spread) && spread>1e-10) (get(v)-center)/spread else NA_real_]
  scale_rows[[v]] <- data.table(variable=v,mean=center,sd=spread,reference_end=train_end)
}
fwrite(rbindlist(scale_rows),file.path(out,'predictor_scales.csv'))
# Source counts are institution-year / field-year variables, already absorbed
# by the main fixed effects. They remain explicit in prediction models.
controls <- 'lag_score + lag_score2 + log_n_previous + log_n_current'
effects <- '| pair_id + skill_id^year + field_id^year + unitid^year'
strict_effects <- '| pair_id + field_id^skill_id^year + unitid^year'
coefs <- list(); samples <- list(); failures <- list(); predictions <- list(); comparisons <- list()
model_diagnostics <- list()

fit_record <- function(sample, outcome, rhs, fe, label, floor, scope) {
  key <- paste(scope,outcome,floor,label,sep='_')
  fitted <- tryCatch(feols(as.formula(paste(outcome,'~',rhs,fe)),data=sample,
                   cluster=~unitid,fixef.rm='none'), error=function(e) e)
  if (inherits(fitted,'error')) {
    failures[[key]] <<- data.table(scope=scope,outcome=outcome,min_syllabi=floor,
                                  model=label,reason=conditionMessage(fitted))
    return(NULL)
  }
  table <- as.data.table(coeftable(fitted), keep.rownames='term')
  setnames(table,c('term','estimate','se','t','p'))
  table[, `:=`(scope=scope,outcome=outcome,min_syllabi=floor,model=label,rows=nobs(fitted))]
  coefs[[key]] <<- table
  model_diagnostics[[key]] <<- data.table(scope=scope,outcome=outcome,min_syllabi=floor,
        model=label,rows=nobs(fitted),within_r2=as.numeric(fitstat(fitted,'wr2')[[1]]),
        dropped_variables=paste(fitted$collin.var,collapse=';'))
  return(fitted)
}

complete_for <- function(data, outcome, floor, variables) {
  coverage <- if (outcome=='delta1') 'coverage1' else 'coverage2'
  sample <- data[get(coverage)>=floor]
  valid <- Reduce(`&`,lapply(sample[,c(outcome,variables),with=FALSE],is.finite))
  sample <- sample[valid]
  repeated <- sample[,.N,by=pair_id][N>=2,pair_id]
  sample[pair_id %in% repeated]
}

# One-step-ahead temporal prediction uses separate models with estimable future
# covariates. Future-year fixed effects cannot be predicted: these models use
# program-skill intercepts and a common trend, fitted on training years only.
forecast <- function(sample,outcome,floor,scope,hiring=NULL) {
  boundary <- if (is.null(hiring)) 2013L else 2015L
  end_year <- if (outcome=='delta1') sample$year else sample$year+1L
  train <- copy(sample[end_year<=boundary])
  test <- copy(sample[year>boundary])
  min_train <- if (is.null(hiring)) 3L else 2L
  ids <- train[,.N,by=pair_id][N>=min_train,pair_id]
  train <- train[pair_id %in% ids]; test <- test[pair_id %in% ids]
  if (nrow(train)<100 || nrow(test)<100 || uniqueN(train$unitid)<10) {
    failures[[paste('forecast',scope,outcome,floor)]] <<- data.table(scope=scope,outcome=outcome,
         min_syllabi=floor,model='forecast',reason='Insufficient repeated training pairs / institutions')
    return(invisible(NULL))
  }
  # Current-year collection count is withheld from prediction; it is unknown at
  # the forecasting origin. Sample eligibility still depends on later coverage.
  predictive_controls <- 'lag_score + lag_score2 + log_n_previous + log_n_inst + log_n_field + time'
  forms <- list(baseline=predictive_controls,
                institution=paste(predictive_controls,'+ same_inst_std'),
                discipline=paste(predictive_controls,'+ same_field_std'),
                both=paste(predictive_controls,'+ same_inst_std + same_field_std'))
  if (!is.null(hiring)) forms <- list(both=forms$both,
              both_plus_hiring=paste(forms$both,'+',paste0(hiring,'_std')))
  predictions_by_model <- list()
  for (name in names(forms)) {
    result <- tryCatch({
      fitted <- feols(as.formula(paste(outcome,'~',forms[[name]],'| pair_id')),
                      data=train,fixef.rm='none',notes=FALSE)
      as.numeric(predict(fitted,newdata=test))
    }, error=function(e) e)
    if (inherits(result,'error')) {
      failures[[paste('forecast',scope,outcome,floor,name)]] <<- data.table(scope=scope,
              outcome=outcome,min_syllabi=floor,model=name,reason=conditionMessage(result))
    } else predictions_by_model[[name]] <- result
  }
  reference <- if (is.null(hiring)) 'baseline' else 'both'
  if (!reference %in% names(predictions_by_model)) return(invisible(NULL))
  keep <- Reduce(`&`, lapply(predictions_by_model,is.finite))
  test <- test[keep]
  predictions_by_model <- lapply(predictions_by_model,function(p) p[keep])
  truth <- test[[outcome]]
  if (!length(truth)) return(invisible(NULL))
  base_error <- (truth-predictions_by_model[[reference]])^2
  for (name in names(predictions_by_model)) {
    predicted <- predictions_by_model[[name]]
    error <- (truth-predicted)^2
    key <- paste(scope,outcome,floor,name)
    predictions[[key]] <<- data.table(scope=scope,outcome=outcome,min_syllabi=floor,model=name,
        train_rows=nrow(train),test_rows=nrow(test),test_institutions=uniqueN(test$unitid),
        train_end_year=boundary,test_start_year=min(test$year),test_end_year=max(test$year),
        rmse=sqrt(mean(error)),mae=mean(abs(truth-predicted)),
        r2_vs_no_change=1-sum(error)/sum(truth^2),
        mse_improvement_vs_reference=1-mean(error)/mean(base_error),reference=reference)
    if (name!=reference) {
      # Paired institution-block bootstrap of held-out losses, retaining row weights.
      losses <- data.table(unitid=test$unitid,difference=base_error-error)
      blocks <- losses[,.(total=sum(difference),count=.N),by=unitid]
      set.seed(20261009)
      draws <- replicate(300,{idx <- sample.int(nrow(blocks),nrow(blocks),replace=TRUE)
                          sum(blocks$total[idx])/sum(blocks$count[idx])})
      comparisons[[key]] <<- data.table(scope=scope,outcome=outcome,min_syllabi=floor,
         model=name,reference=reference,mean_squared_loss_improvement=mean(base_error-error),
         ci_low=unname(quantile(draws,.025)),ci_high=unname(quantile(draws,.975)),
         bootstrap_institutions=nrow(blocks),bootstrap_replicates=300)
    }
  }
  yearly <- rbindlist(lapply(names(predictions_by_model),function(name) {
    temp <- data.table(year=test$year,error=(truth-predictions_by_model[[name]])^2)
    temp[,.(model=name,rows=.N,rmse=sqrt(mean(error))),by=year]
  }))
  fwrite(yearly,file.path(out,paste0('forecast_by_year_',scope,'_',outcome,'_',floor,'.csv')))
}

for (floor in c(9L,3L)) for (outcome in c('delta1','delta2')) {
  message('Main models: ',outcome,'; syllabi >= ',floor)
  generic <- complete_for(dt,outcome,floor,c('lag_score','same_inst_std','same_field_std'))
  samples[[paste(outcome,floor)]] <- data.table(scope='main',outcome=outcome,min_syllabi=floor,
       rows=nrow(generic),institutions=uniqueN(generic$unitid),programs=uniqueN(generic$cell_id),
       skills=uniqueN(generic$skill_id),first_year=min(generic$year),last_year=max(generic$year))
  if (nrow(generic)<100) next
  specifications <- list(baseline=controls,institution=paste(controls,'+ same_inst_std'),
       discipline=paste(controls,'+ same_field_std'),
       both=paste(controls,'+ same_inst_std + same_field_std'))
  for (name in names(specifications)) fit_record(generic,outcome,specifications[[name]],
                                               effects,name,floor,'main')
  # National discipline-skill-year shocks absorb the generic discipline signal.
  # Estimate ONLY the within-institution channel in this stricter specification.
  fit_record(generic,outcome,paste(controls,'+ same_inst_std'),strict_effects,
             'institution_with_discipline_skill_shocks',floor,'main')
  forecast(generic,outcome,floor,'main')
  for (hiring in c('hiring2015','hiring2022')) {
    scope <- if (hiring=='hiring2015') 'network2015_post2013' else 'network2022_retrospective'
    pool <- dt[year>=2014 & get(paste0('n_',hiring))>=2 & get(paste0('share_',hiring))>=.5]
    subset <- complete_for(pool,outcome,floor,c('lag_score','same_inst_std','same_field_std',paste0(hiring,'_std')))
    samples[[paste(scope,outcome,floor)]] <- data.table(scope=scope,outcome=outcome,min_syllabi=floor,
       rows=nrow(subset),institutions=uniqueN(subset$unitid),programs=uniqueN(subset$cell_id),
       skills=uniqueN(subset$skill_id),first_year=if(nrow(subset)) min(subset$year) else NA,
       last_year=if(nrow(subset)) max(subset$year) else NA)
    if (nrow(subset)<100 || uniqueN(subset$unitid)<10) {
      failures[[paste(scope,outcome,floor)]] <- data.table(scope=scope,outcome=outcome,
           min_syllabi=floor,model='network_models',reason='Too few eligible mapped institutions')
      next
    }
    rhs <- paste(controls,'+ same_inst_std + same_field_std +',
                 paste0('log1p(n_',hiring,') + share_',hiring))
    fit_record(subset,outcome,rhs,effects,'both_same_network_sample',floor,scope)
    fit_record(subset,outcome,paste(rhs,'+',paste0(hiring,'_std')),effects,
               'both_plus_hiring',floor,scope)
    if (hiring=='hiring2015' && outcome=='delta1') forecast(subset,outcome,floor,scope,hiring)
  }
}
tables <- rbindlist(coefs,fill=TRUE)
if (!nrow(tables) || !any(tables$scope=='main')) stop('No main model completed successfully')
tables[, p_bh := p.adjust(p,method='BH'),by=.(scope,outcome,min_syllabi)]
fwrite(tables,file.path(out,'coefficients.csv'))
fwrite(rbindlist(samples,fill=TRUE),file.path(out,'model_samples.csv'))
fwrite(rbindlist(model_diagnostics,fill=TRUE),file.path(out,'model_diagnostics.csv'))
fwrite(rbindlist(predictions,fill=TRUE),file.path(out,'out_of_sample.csv'))
fwrite(rbindlist(comparisons,fill=TRUE),file.path(out,'out_of_sample_comparisons.csv'))
if (length(failures)) fwrite(rbindlist(failures,fill=TRUE),file.path(out,'skipped_or_failed_models.csv'))
report <- capture.output({
  cat('FIRST CONTENT-CHANNEL PILOT — no RCA; exploratory associations\n\n')
  cat('delta1: annual inferred-score change / baseline SD.\n')
  cat('delta2: two-year net change / 2 / baseline SD; requires three observed consecutive profiles.\n')
  cat('Primary coverage: >=9 syllabi in each relevant year; >=3 sensitivity.\n')
  cat('Source profiles require >=3 syllabi. All model comparisons within a scope share a sample.\n')
  cat('Fixed effects: program-skill, skill-year, field-year, institution-year.\n')
  cat('Strict internal-channel model adds field-skill-year shocks and omits the discipline channel.\n')
  cat('Held-out main predictions: train endpoints <=2013; target years >=2014.\n')
  cat('Prediction models use train-only program-skill intercepts and time trend; no unseen-year effects.\n')
  cat('Hiring-2015 predictions: train 2014–2015, test 2016–2017; eligible repeated pairs only.\n')
  cat('Hiring-2022: retrospective sensitivity only; never treated as a prospective test.\n\n')
  print(rbindlist(samples,fill=TRUE))
  cat('\nCHANNEL COEFFICIENTS\n')
  print(tables[grepl('_std$',term),.(scope,outcome,min_syllabi,model,term,estimate,se,p,p_bh)])
  cat('\nHELD-OUT PREDICTION\n')
  print(rbindlist(predictions,fill=TRUE))
  cat('\nPAIRED HELD-OUT LOSS COMPARISONS (positive = improvement)\n')
  print(rbindlist(comparisons,fill=TRUE))
  cat('\nNo dated hiring-event or collaboration mechanism is identified. No labor-market returns are estimated.\n')
  cat('Generic peer content can reflect common shocks or sorting. Predictive improvement is not transmission.\n')
  cat('Short-panel lagged-outcome estimates may have dynamic-panel bias.\n')
  cat('Coverage filters change the population; follow-up eligibility conditions persistence diagnostics.\n')
  if (length(failures)) {cat('\nSKIPPED / FAILED MODELS\n');print(rbindlist(failures,fill=TRUE))}
})
writeLines(report,file.path(out,'summary.txt'))
writeLines('completed',file.path(out,'models_complete.txt'))
cat(paste(report,collapse='\n'),'\n')
