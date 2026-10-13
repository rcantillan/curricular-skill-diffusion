suppressPackageStartupMessages({library(data.table);library(fixest)})
setDTthreads(2L);setFixest_nthreads(2L)
out=commandArgs(TRUE)[1]
d=fread(file.path(out,'panel.csv.gz'))
stopifnot(!anyDuplicated(d[,.(cell_id,skill_id,year)]),all(d$incorporation %in% 0:1))
d[,`:=`(pair_id=.GRP),by=.(cell_id,skill_id)]
d[,`:=`(lag_score2=lag_score^2,previous_change2=previous_change^2,
 log_old=log(n_old),log_lag=log(n_lag),log_current=log(n_current),
 log_within=log1p(n_within),log_same=log1p(n_same_field),log_other=log1p(n_other_field))]
controls=c('lag_score','lag_score2','previous_change','previous_change2',
 'log_old','log_lag','log_current','log_within','log_same','log_other')
# Future counts are only selection diagnostics, never predictors.
models=list(channels=c('within','same_field','other_field'),
 strict_channels=c('within','other_field'),
 foreign_content=c('within','other_field','within_distinct','other_distinct'),
 status_same_field=c('within','other_field','status_above','status_below'))
institutional='sel_above_same' %in% names(d)
if(institutional){
 models$status_same_field=NULL
 ordinary=c('within','other_field','matched_same','matched_other')
 direction=c('sel_above_same','sel_below_same','sel_above_other','sel_below_other')
 capacity=c('instruction_gap_same','instruction_gap_other','research_gap_same','research_gap_other',
   'same_type_same','same_type_other','same_control_same','same_control_other')
 models$selectivity_base=ordinary
 models$selectivity_direction=c(ordinary,direction)
 models$selectivity_adjusted=c(ordinary,direction,capacity)
}
coefs=list();influences=list();failures=list();diagnostics=list()
base_channels=c('within','same_field','other_field')
primary=d[complete.cases(d[,..base_channels])]
for(label in names(models)){
 channels=models[[label]]
 sample=primary[complete.cases(primary[,..channels])]
 if(grepl('^selectivity_',label)){
  sample=primary[profile_fraction_same>=.5 & profile_fraction_other>=.5]
  all_vars=unique(models$selectivity_adjusted)
  sample=sample[complete.cases(sample[,..all_vars])]
 }
 ids=sample[,.N,by=pair_id][N>=2,pair_id];sample=sample[pair_id %in% ids]
 diagnostics[[label]]=data.table(model=label,rows=nrow(sample),entries=sum(sample$incorporation),
   programs=uniqueN(sample$cell_id),institutions=uniqueN(sample$unitid),
   unfiltered_rows=nrow(d),unfiltered_entries=sum(d$incorporation))
 tryCatch({
  if(nrow(sample)<1000||uniqueN(sample$unitid)<10||sum(sample$incorporation)<20)
    stop('Insufficient repeated receivers, institutions or entries')
  effects=if(label=='channels')'|pair_id+skill_id^year+field_id^year+unitid^year' else
     '|pair_id+field_id^skill_id^year+unitid^year'
  extra=if(grepl('^selectivity_',label))c('age_same','age_other','profile_fraction_same','profile_fraction_other')else character()
  m=feols(as.formula(paste('incorporation~',paste(c(controls,extra,channels),collapse='+'),effects)),sample,
     cluster=~unitid,fixef.rm='none',demeaned=TRUE,notes=FALSE)
  stopifnot(nobs(m)==nrow(sample))
  ct=as.data.table(coeftable(m),keep.rownames='term');setnames(ct,c('term','estimate','se','t','p'))
  ct=ct[term %in% channels];if(!nrow(ct))stop('All exposures absorbed')
  x=m$X_demeaned[,names(coef(m)),drop=FALSE];bread=m$cov.unscaled/m$sigma2
  inf=rowsum(x*as.numeric(m$residuals),sample$unitid,reorder=TRUE)%*%bread
  colnames(inf)=names(coef(m))
  adjustment=median((diag(vcov(m))/colSums(inf^2))[is.finite(diag(vcov(m))/colSums(inf^2)) & colSums(inf^2)>0])
  stopifnot(is.finite(adjustment),adjustment>0);inf=inf*sqrt(adjustment)
  stopifnot(max(abs(sqrt(colSums(inf[,ct$term,drop=FALSE]^2))-ct$se)/pmax(ct$se,1e-12))<1e-5)
  ct[,`:=`(model=label,rows=nobs(m))];coefs[[label]]=ct
  ii=as.data.table(inf[,ct$term,drop=FALSE]);ii[,unitid:=as.integer(rownames(inf))]
  ii=melt(ii,id.vars='unitid',variable.name='term',value.name='influence');ii[,model:=label]
  influences[[label]]=ii
  if(length(setdiff(channels,ct$term)))failures[[paste0(label,'_dropped')]]=data.table(model=label,
      reason=paste('Absorbed channels:',paste(setdiff(channels,ct$term),collapse=';')))
 },error=function(e){failures[[label]]<<-data.table(model=label,reason=conditionMessage(e))})
}
if(length(coefs))fwrite(rbindlist(coefs),file.path(out,'coefficients.csv'))
if(length(influences))fwrite(rbindlist(influences),file.path(out,'influences.csv.gz'))
if(length(failures))fwrite(rbindlist(failures),file.path(out,'failures.csv'))
fwrite(rbindlist(diagnostics),file.path(out,'model_support.csv'))
writeLines('{"complete":true}',file.path(out,'complete.json'))
