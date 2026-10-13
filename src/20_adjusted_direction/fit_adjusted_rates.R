suppressPackageStartupMessages({library(data.table);library(fixest)})
setDTthreads(2L);setFixest_nthreads(2L)
out=commandArgs(TRUE)[1];d=fread(file.path(out,'panel.csv.gz'))
stopifnot(!anyDuplicated(d[,.(cell_id,skill_id,year)]))
d[,pair_id:=.GRP,by=.(cell_id,skill_id)]
d[,`:=`(lag_score2=lag_score^2,previous_change2=previous_change^2,
 log_old=log(n_old),log_lag=log(n_lag),log_current=log(n_current),
 log_within=log1p(n_within),log_same=log1p(n_same_field),log_other=log1p(n_other_field))]
history=c('lag_score','lag_score2','previous_change','previous_change2','log_old','log_lag','log_current','log_within','log_same','log_other')
extra=c('within','other_field','matched_same','matched_other','instruction_gap_same','instruction_gap_other',
 'research_gap_same','research_gap_other','same_type_same','same_type_other','same_control_same','same_control_other',
 'age_same','age_other','profile_fraction_same','profile_fraction_other')
allvars=c(history,extra,'same_field');rates=list();influences=list();supports=list();coefficients=list()
bin_names=c('down_far','down_near','horizontal','up_near','up_far');terms=bin_names[-3]
for(channel in c('same','other')){
 wcols=paste0('w_',channel,'_',0:4)
 sample=d[complete.cases(d[,..allvars]) & profile_fraction_same>=.5 & profile_fraction_other>=.5]
 sample=sample[rowSums(sample[,..wcols])>.999999]
 # Identical repeated receiver population and common field-year support for both specifications.
 for(iter in 1:100){
  before=nrow(sample)
  repeated=sample[,.N,by=pair_id][N>=2,pair_id];sample=sample[pair_id %in% repeated]
  tab=sample[,lapply(.SD,sum),by=.(field_id,year),.SDcols=wcols]
  common=tab[apply(as.matrix(tab[,..wcols]),1,min)>=10,.(field_id,year)]
  sample=sample[common,on=.(field_id,year),nomatch=0]
  if(nrow(sample)==before)break
 }
 stopifnot(nrow(sample)>=1000,uniqueN(sample$unitid)>=10,sum(sample$incorporation)>=20)
 n=nrow(sample);mean_y=mean(sample$incorporation);pi=colMeans(sample[,..wcols])
 sample[,receiver_row:=.I]
 stacked=melt(sample,id.vars=setdiff(names(sample),wcols),measure.vars=wcols,variable.name='direction',value.name='weight')
 stacked=stacked[weight>0];stacked[,bin:=match(as.character(direction),wcols)-1L]
 for(b in c(0,1,3,4))stacked[,(bin_names[b+1]):=as.integer(bin==b)]
 stopifnot(abs(sum(stacked$weight)-n)<1e-7*n)
 for(label in c('strict_history','institutional_adjusted')){
  controls=if(label=='strict_history')history else c(history,extra)
  f=as.formula(paste('incorporation~',paste(c(terms,controls),collapse='+'),'|pair_id+field_id^skill_id^year+unitid^year'))
  m=feols(f,stacked,weights=~weight,cluster=~unitid,ssc=ssc(K.adj=FALSE,G.adj=TRUE),fixef.rm='none',demeaned=TRUE,notes=FALSE)
  stopifnot(nobs(m)==nrow(stacked),all(terms %in% names(coef(m))))
  x=m$X_demeaned[,names(coef(m)),drop=FALSE];bread=m$cov.unscaled/m$sigma2
  inf=rowsum(x*(stacked$weight*as.numeric(m$residuals)),stacked$unitid,reorder=TRUE)%*%bread
  colnames(inf)=names(coef(m))
  ratio=diag(vcov(m))/colSums(inf^2);adjustment=median(ratio[is.finite(ratio)&ratio>0]);inf=inf*sqrt(adjustment)
  stopifnot(max(abs(sqrt(colSums(inf[,terms,drop=FALSE]^2))-sqrt(diag(vcov(m))[terms]))/pmax(sqrt(diag(vcov(m))[terms]),1e-12))<1e-5)
  beta=setNames(rep(0,5),bin_names);beta[terms]=coef(m)[terms]
  base=mean_y-sum(pi*beta);adjusted=base+beta
  # Influence of the shared receiver mean and estimated direction composition,
  # plus coefficient influence. This retains covariance across rates and blocks.
  mean_component=sample[,.(value=sum(incorporation-mean_y-as.numeric(as.matrix(.SD)%*%beta)+sum(pi*beta))/n),by=unitid,.SDcols=wcols]
  mean_component=setNames(mean_component$value,mean_component$unitid)
  for(b in 0:4){
   contrast=-pi;contrast[b+1]=contrast[b+1]+1
   value=as.numeric(inf[,terms,drop=FALSE]%*%contrast[c(1,2,4,5)])+mean_component[rownames(inf)]
   rates[[length(rates)+1]]=data.table(channel=channel,model=label,bin=b,rate=adjusted[b+1],
      raw_rate=sum(sample[[wcols[b+1]]]*sample$incorporation)/sum(sample[[wcols[b+1]]]),
      receivers=n,weighted_opportunities=sum(sample[[wcols[b+1]]]))
   influences[[length(influences)+1]]=data.table(channel=channel,model=label,bin=b,unitid=as.integer(rownames(inf)),influence=value)
  }
  supports[[length(supports)+1]]=data.table(channel=channel,model=label,receivers=n,entries=sum(sample$incorporation),
     stacked_rows=nrow(stacked),institutions=uniqueN(sample$unitid),common_strata=nrow(common),
     adjusted_rates_outside_unit_interval=sum(adjusted<0|adjusted>1),min_adjusted_rate=min(adjusted),max_adjusted_rate=max(adjusted))
  ct=as.data.table(coeftable(m),keep.rownames='term');ct=ct[term %in% terms];ct[,`:=`(channel=channel,model=label)]
  coefficients[[length(coefficients)+1]]=ct
 }
}
fwrite(rbindlist(rates),file.path(out,'rates.csv'));fwrite(rbindlist(influences),file.path(out,'influences.csv.gz'))
fwrite(rbindlist(supports),file.path(out,'model_support.csv'));fwrite(rbindlist(coefficients),file.path(out,'coefficients.csv'))
writeLines('{"complete":true}',file.path(out,'complete.json'))
