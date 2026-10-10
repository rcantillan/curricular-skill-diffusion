suppressPackageStartupMessages({library(data.table);library(fixest)})
setDTthreads(2L);setFixest_nthreads(2L)
args=commandArgs(TRUE);stopifnot(length(args)==1)
out=args[1];d=fread(file.path(out,'program_year_changes.csv.gz'))
tables=list();diagnostics=list();failures=list()
outcomes=c('change_abs','change_rms','two_year_abs','category_change_abs','category_two_year_abs','category_js_divergence')
outcomes=intersect(outcomes,names(d))
for(floor in c(3L,9L,20L)) for(y in outcomes){
  sub=d[min_syllabi==floor & community>=0 & is.finite(get(y))]
  key=paste(y,floor)
  if(nrow(sub)<100 || uniqueN(sub$unitid)<10){
    failures[[key]]=data.table(outcome=y,min_syllabi=floor,reason='Insufficient eligible rows/institutions');next
  }
  tryCatch({
    # Community is fixed at baseline; program fixed effects would absorb it.
    # This is a conditional descriptive comparison, not a causal effect.
    m=feols(as.formula(paste(y,'~ i(community) + log(n_previous) + log(n_current) + baseline_years | field^year + unitid')),
            data=sub,cluster=~unitid,notes=FALSE)
    ct=as.data.table(coeftable(m),keep.rownames='term');setnames(ct,c('term','estimate','se','t','p'))
    ct[,`:=`(outcome=y,min_syllabi=floor,rows=nobs(m),institutions=uniqueN(sub$unitid))]
    tables[[key]]=ct
    test=wald(m,keep='community::',print=FALSE)
    diagnostics[[key]]=data.table(outcome=y,min_syllabi=floor,rows=nobs(m),institutions=uniqueN(sub$unitid),
                                 community_wald_p=if(is.list(test))test$p else NA_real_,
                                 dropped_terms=paste(m$collin.var,collapse=';'))
  },error=function(e){failures[[key]]<<-data.table(outcome=y,min_syllabi=floor,reason=conditionMessage(e))})
}
if(length(tables))fwrite(rbindlist(tables),file.path(out,'adjusted_community_coefficients.csv'))
if(length(diagnostics))fwrite(rbindlist(diagnostics),file.path(out,'adjusted_community_tests.csv'))
if(length(failures))fwrite(rbindlist(failures),file.path(out,'skipped_models.csv'))
if(!length(tables))stop('No adjusted comparison could be estimated')
