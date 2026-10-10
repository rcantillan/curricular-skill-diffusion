suppressPackageStartupMessages({library(data.table);library(fixest)})
setDTthreads(2L);setFixest_nthreads(2L)
args=commandArgs(TRUE);stopifnot(length(args)==2);out=args[1]
d=fread(file.path(out,'panel.csv.gz'));fields=fread(args[2])
channels=c('internal','external_same','external_other')
signals=unlist(lapply(channels,function(x)paste0(x,c('_stock','_increase'))))
random=paste0('random_',signals);leads=paste0(channels,'_future_increase')
d[,`:=`(lag_score2=lag_score^2,previous_positive=pmax(previous_change,0),
         log_previous=log(n_previous),log_current=log(n_current),time=year-2008)]
d[,pair:=.GRP,by=.(node_id,skill_id)]
coverage=grep('_(coverage|count)$',names(d),value=TRUE)
for(name in grep('_count$',coverage,value=TRUE))d[,(name):=log(get(name))]
generic=grep('^generic_',names(d),value=TRUE)
controls=c('lag_score','lag_score2','previous_change','previous_positive','log_previous',generic,coverage)
coefs=list();influences=list();failures=list();diagnostics=list();losses=list();tuning=list()
fit=function(data,rhs,label){
 tryCatch({
  m=feols(as.formula(paste('delta1~',paste(c(controls,'log_current',rhs),collapse='+'),
                         '|pair+field_id^skill_id^year+unitid^year')),data,
          cluster=~unitid,fixef.rm='none',demeaned=TRUE,notes=FALSE)
  ct=as.data.table(coeftable(m),keep.rownames='term');setnames(ct,c('term','estimate','se','t','p'))
  ct=ct[term %in% rhs];if(!nrow(ct))stop('No channel term estimable')
  if(length(setdiff(rhs,ct$term)))failures[[paste0(label,'_dropped')]]<<-data.table(model=label,reason=paste('Dropped:',paste(setdiff(rhs,ct$term),collapse=';')))
  x=m$X_demeaned[,names(coef(m)),drop=FALSE];bread=m$cov.unscaled/m$sigma2
  inf=rowsum(x*as.numeric(m$residuals),data$unitid,reorder=TRUE)%*%bread;colnames(inf)=names(coef(m))
  adjustment=median(diag(vcov(m))/colSums(inf^2),na.rm=TRUE);inf=inf*sqrt(adjustment)
  stopifnot(max(abs(sqrt(colSums(inf[,ct$term,drop=FALSE]^2))-ct$se)/pmax(ct$se,1e-12))<1e-5)
  ct[,`:=`(model=label,rows=nobs(m))];coefs[[label]]<<-ct
  ii=as.data.table(inf[,ct$term,drop=FALSE]);ii[,unitid:=as.integer(rownames(inf))]
  ii=melt(ii,id.vars='unitid',variable.name='term',value.name='influence');ii[,model:=label];influences[[label]]<<-ii
  correlation=cor(x[,ct$term,drop=FALSE]);eigenvalues=eigen(correlation,symmetric=TRUE,only.values=TRUE)$values
  diagnostics[[label]]<<-data.table(model=label,rows=nobs(m),institutions=uniqueN(data$unitid),
      channel_correlation_min_eigenvalue=min(eigenvalues),dropped=paste(m$collin.var,collapse=';'))
 },error=function(e){failures[[label]]<<-data.table(model=label,reason=conditionMessage(e))})
}

# Joint ridge regularizes slopes as well as program-activity intercepts. Scales,
# coefficients, and intercepts are estimated from the training period only.
ridge=function(train,test,features,alpha,pair_penalty){
 x=as.matrix(train[,..features]);xt=as.matrix(test[,..features]);mu=colMeans(x);sd=apply(x,2,sd)
 sd[!is.finite(sd)|sd<1e-10]=1
 x=cbind(1,sweep(sweep(x,2,mu),2,sd,'/'));xt=cbind(1,sweep(sweep(xt,2,mu),2,sd,'/'))
 sx=rowsum(x,as.character(train$pair),reorder=TRUE);sy=rowsum(train$delta1,as.character(train$pair),reorder=TRUE)[,1]
 nn=rowsum(rep(1,nrow(train)),as.character(train$pair),reorder=TRUE)[,1];den=nn+pair_penalty
 penalty=diag(c(1e-8,rep(alpha*nrow(train),ncol(x)-1)))
 beta=solve(crossprod(x)-crossprod(sx,sx/den)+penalty,crossprod(x,train$delta1)-crossprod(sx,sy/den))
 a=(sy-as.numeric(sx%*%beta))/den
 result=as.numeric(xt%*%beta)+a[match(as.character(test$pair),rownames(sx))]
 stopifnot(all(is.finite(result)));result
}

forecast=function(data){
 data=copy(data)
 dummy=model.matrix(~factor(field_id)+factor(skill_id),data=data)[,-1,drop=FALSE]
 for(j in seq_len(ncol(dummy)))data[,(paste0('dummy',j)):=dummy[,j]]
 base=c(controls,'time',paste0('dummy',seq_len(ncol(dummy))))
 specifications=list(baseline=base,internal=c(base,signals[grepl('^internal_',signals)]),
   external_same=c(base,signals[grepl('^external_same_',signals)]),
   external_other=c(base,signals[grepl('^external_other_',signals)]),all=c(base,signals),random=c(base,random))
 candidates=CJ(alpha=c(.0001,.01,1),pair_penalty=c(3,30))
 validation=list()
 for(cutoff in 2011:2013){
  train=data[year<cutoff];ids=train[,.N,by=pair][N>=2,pair];train=train[pair %in% ids]
  test=data[year==cutoff & pair %in% ids]
  if(nrow(train)>=100&&nrow(test)>=100&&uniqueN(test$unitid)>=10)validation[[as.character(cutoff)]]=list(train=train,test=test)
 }
 if(length(validation)<2)stop('Insufficient chronological validation folds')
 train=data[year<=2013];ids=train[,.N,by=pair][N>=3,pair];train=train[pair %in% ids]
 test=data[year>=2014 & pair %in% ids]
 if(nrow(test)<100||uniqueN(test$unitid)<10)stop('Insufficient held-out known programs')
 predictions=list()
 for(name in names(specifications)){
  features=specifications[[name]]
  errors=sapply(seq_len(nrow(candidates)),function(i){
   sse=0;n=0
   for(fold in validation){
    prediction=ridge(fold$train,fold$test,features,candidates$alpha[i],candidates$pair_penalty[i])
    sse=sse+sum((fold$test$delta1-prediction)^2);n=n+length(prediction)
   };sse/n
  })
  best=which.min(errors);t=copy(candidates);t[,`:=`(model=name,validation_mse=errors,chosen=seq_len(.N)==best)]
  tuning[[name]]<<-t
  predictions[[name]]=ridge(train,test,features,candidates$alpha[best],candidates$pair_penalty[best])
 }
 base_error=(test$delta1-predictions$baseline)^2
 for(name in names(predictions)){
  tmp=test[,.(unitid,field_id)];tmp[,`:=`(sse=(test$delta1-predictions[[name]])^2,zero_sse=test$delta1^2,base_sse=base_error)]
  tmp=merge(tmp,fields,by='field_id')
  group=tmp[,.(n=.N,sse=sum(sse),zero_sse=sum(zero_sse),base_sse=sum(base_sse)),by=.(unitid,field)]
  all=tmp[,.(n=.N,sse=sum(sse),zero_sse=sum(zero_sse),base_sse=sum(base_sse)),by=unitid];all[,field:='All fields']
  group=rbind(group,all);group[,model:=name];losses[[name]]<<-group
 }
}

ids=d[,.N,by=pair][N>=2,pair];sub=d[pair %in% ids]
fit(sub,signals,'related');fit(sub,random,'random')
lead=sub[lead_evaluable==TRUE];ids=lead[,.N,by=pair][N>=2,pair];lead=lead[pair %in% ids]
if(nrow(lead)>=100&&uniqueN(lead$unitid)>=10){
 fit(lead,signals,'related_on_lead_sample')
 fit(lead,c(signals,leads),'related_with_future_sources')
}else failures[['lead']]=data.table(model='lead',reason='Insufficient future-source comparison support')
tryCatch(forecast(d),error=function(e){failures[['forecast']]<<-data.table(model='forecast',reason=conditionMessage(e))})
if(length(coefs))fwrite(rbindlist(coefs),file.path(out,'coefficients.csv'))
if(length(influences))fwrite(rbindlist(influences),file.path(out,'influences.csv.gz'))
if(length(losses))fwrite(rbindlist(losses),file.path(out,'losses.csv.gz'))
if(length(failures))fwrite(rbindlist(failures),file.path(out,'failures.csv'))
if(length(diagnostics))fwrite(rbindlist(diagnostics),file.path(out,'diagnostics.csv'))
if(length(tuning))fwrite(rbindlist(tuning),file.path(out,'forecast_tuning.csv'))
if(!length(coefs))stop('No association model succeeded')
writeLines('{"complete":true}',file.path(out,'complete.json'))
