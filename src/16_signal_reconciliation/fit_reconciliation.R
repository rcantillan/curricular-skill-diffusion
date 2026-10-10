suppressPackageStartupMessages({library(data.table);library(fixest)})
setDTthreads(2L);setFixest_nthreads(2L)
args=commandArgs(TRUE);stopifnot(length(args)==2);out=args[1]
d=fread(file.path(out,'panel.csv.gz'));scales=fread(args[2])
for(name in c('same_inst','same_field')){
 sc=scales[channel==name]
 stopifnot(nrow(sc)==1,is.finite(sc$sd),sc$sd>0)
 d[,(paste0(name,'_std')):=(get(name)-sc$mean)/sc$sd]
}
d[,`:=`(lag_score2=lag_score^2,log_n_previous=log(n_previous),log_n_current=log(n_current),
         previous_positive=pmax(previous_change,0),previous_change2=previous_change^2,
         log_n_inst=log1p(n_inst),log_n_field=log1p(n_field),
         lag_over_inst=lag_score/n_inst,lag_over_field=lag_score/n_field,
         previous_over_inst=previous_change/n_inst,previous_over_field=previous_change/n_field)]
d[,pair_id:=.GRP,by=.(cell_id,skill_id)]
base=c('lag_score','lag_score2','log_n_previous','log_n_current')
specifications=list(legacy=base,own_trend=c(base,'previous_change'),
 nonlinear_trend=c(base,'previous_change','previous_positive','previous_change2'),
 source_support=c(base,'previous_change','previous_positive','previous_change2',
   'log_n_inst','log_n_field','lag_over_inst','lag_over_field','previous_over_inst','previous_over_field'))
effects=list(pooled='|pair_id+skill_id^year+field_id^year+unitid^year',
             strict='|pair_id+field_id^skill_id^year+unitid^year')
coefficients=list();influences=list();diagnostics=list();supports=list();failures=list()

fit=function(data,sample,specification,effect){
 key=paste(sample,specification,effect)
 channels=if(effect=='pooled')c('same_inst_std','same_field_std')else 'same_inst_std'
 controls=specifications[[specification]]
 tryCatch({
  m=feols(as.formula(paste('delta1~',paste(c(controls,channels),collapse='+'),effects[[effect]])),
    data,cluster=~unitid,fixef.rm='none',demeaned=TRUE,notes=FALSE)
  stopifnot(nobs(m)==nrow(data))
  ct=as.data.table(coeftable(m),keep.rownames='term');setnames(ct,c('term','estimate','se','t','p'))
  ct=ct[term %in% channels];if(!nrow(ct))stop('No channel estimable')
  x=m$X_demeaned[,names(coef(m)),drop=FALSE];bread=m$cov.unscaled/m$sigma2
  inf=rowsum(x*as.numeric(m$residuals),data$unitid,reorder=TRUE)%*%bread;colnames(inf)=names(coef(m))
  adjustment=diag(vcov(m))/colSums(inf^2);adjustment=median(adjustment[is.finite(adjustment)&adjustment>0])
  stopifnot(is.finite(adjustment));inf=inf*sqrt(adjustment)
  stopifnot(max(abs(sqrt(colSums(inf[,ct$term,drop=FALSE]^2))-ct$se)/pmax(ct$se,1e-12))<1e-5)
  ct[,`:=`(sample=sample,specification=specification,effects=effect,rows=nobs(m))]
  coefficients[[key]]<<-ct
  ii=as.data.table(inf[,ct$term,drop=FALSE]);ii[,unitid:=as.integer(rownames(inf))]
  ii=melt(ii,id.vars='unitid',variable.name='term',value.name='influence')
  ii[,`:=`(sample=sample,specification=specification,effects=effect)];influences[[key]]<<-ii
  diagnostics[[key]]<<-data.table(sample=sample,specification=specification,effects=effect,rows=nobs(m),
    institutions=uniqueN(data$unitid),dropped=paste(m$collin.var,collapse=';'),estimable_channel=TRUE)
  if(length(setdiff(channels,ct$term)))failures[[paste0(key,'_dropped')]]<<-data.table(sample=sample,specification=specification,effects=effect,reason=paste('Dropped channel:',paste(setdiff(channels,ct$term),collapse=';')))
 },error=function(e){failures[[key]]<<-data.table(sample=sample,specification=specification,effects=effect,reason=conditionMessage(e))})
}

available=d[is.finite(same_inst_std)&is.finite(same_field_std)]
samples=list(legacy_full=available,history3=available[n_old>=3],history9=available[n_old>=9],
             boundary_receivers=available[boundary_selected==TRUE])
for(label in names(samples)){
 sample=copy(samples[[label]]);ids=sample[,.N,by=pair_id][N>=2,pair_id];sample=sample[pair_id %in% ids]
 supports[[label]]=sample[,.(programs=uniqueN(cell_id),institutions=uniqueN(unitid),activity_rows=.N),by=.(year,field_id)]
 supports[[label]][,sample:=label]
 if(nrow(sample)<100||uniqueN(sample$unitid)<10){failures[[label]]=data.table(sample=label,specification='all',effects='all',reason='Insufficient repeated receivers');next}
 steps=if(label=='legacy_full')'legacy'else names(specifications)
 for(step in steps)for(effect in names(effects))fit(sample,label,step,effect)
}

# Exact algebraic limitation of an equal-program internal source mean:
# internal_std + own_lag / (n_internal * channel_SD) is constant within
# institution × activity × year. An institutional activity shock can therefore
# account for the same regressor. Saturating that cell does not test "no diffusion".
structural=copy(samples$legacy_full)
channel_sd=scales[channel=='same_inst',sd]
structural[,identity:=same_inst_std+lag_score/(n_inst*channel_sd)]
range=structural[,.(spread=max(identity)-min(identity)),by=.(unitid,skill_id,year)]
stopifnot(max(range$spread)<1e-8)
fwrite(data.table(diagnostic='internal_mean_identity',maximum_within_cell_spread=max(range$spread),
 expected_absorption=TRUE,interpretation='Equal-weight internal means cannot separate transmission from institution-activity-year shocks once own-lag denominator is controlled.'),file.path(out,'identification_diagnostic.csv'))

if(length(coefficients))fwrite(rbindlist(coefficients),file.path(out,'coefficients.csv'))
if(length(influences))fwrite(rbindlist(influences),file.path(out,'influences.csv.gz'))
if(length(diagnostics))fwrite(rbindlist(diagnostics),file.path(out,'diagnostics.csv'))
if(length(supports))fwrite(rbindlist(supports),file.path(out,'support.csv'))
if(length(failures))fwrite(rbindlist(failures),file.path(out,'failures.csv'))
if(!length(coefficients))stop('No model succeeded')
writeLines('{"complete":true}',file.path(out,'complete.json'))
