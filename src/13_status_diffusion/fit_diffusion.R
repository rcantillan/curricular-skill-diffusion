suppressPackageStartupMessages({library(data.table);library(fixest)})
setDTthreads(2L);setFixest_nthreads(2L)
args=commandArgs(TRUE);stopifnot(length(args)==1);out=args[1]
d=fread(file.path(out,'panel.csv.gz'))
d[,`:=`(lag_score2=lag_score^2,log_previous=log(n_previous),log_current=log(n_current),log_sources=log(n_sources),time=year-2014)]
d[,pair:=.GRP,by=.(node_id,skill_id)]
controls='lag_score+lag_score2+previous_change+previous_positive+previous_positive_over_peers+log_previous+log_current'
effects='|pair+field_id^skill_id^year+unitid^year'
coefs=list();influences=list();losses=list();failures=list();diagnostics=list();penalties=list()
features=c('direction_flow','signed_gap_flow','absolute_gap_flow')
fit=function(data,y,rhs,label,floor){
 key=paste(y,label,floor)
 tryCatch({
  m=feols(as.formula(paste(y,'~',controls,'+',rhs,effects)),data,cluster=~unitid,fixef.rm='none',demeaned=TRUE,notes=FALSE)
  ct=as.data.table(coeftable(m),keep.rownames='term');setnames(ct,c('term','estimate','se','t','p'))
  ct=ct[grepl('_flow',term)];if(!nrow(ct))stop('No status moment estimable')
  x=m$X_demeaned[,names(coef(m)),drop=FALSE];bread=m$cov.unscaled/m$sigma2
  inf=rowsum(x*as.numeric(m$residuals),data$unitid,reorder=TRUE)%*%bread;colnames(inf)=names(coef(m))
  adjustment=median(diag(vcov(m))/colSums(inf^2),na.rm=TRUE);inf=inf*sqrt(adjustment)
  stopifnot(max(abs(sqrt(colSums(inf[,ct$term,drop=FALSE]^2))-ct$se)/pmax(ct$se,1e-12))<1e-5)
  ct[,`:=`(outcome=y,min_syllabi=floor,model=label,rows=nobs(m))];coefs[[key]]<<-ct
  ii=as.data.table(inf[,ct$term,drop=FALSE]);ii[,unitid:=as.integer(rownames(inf))]
  ii=melt(ii,id.vars='unitid',variable.name='term',value.name='influence');ii[,`:=`(outcome=y,min_syllabi=floor,model=label)]
  influences[[key]]<<-ii
  diagnostics[[key]]<<-data.table(outcome=y,min_syllabi=floor,model=label,rows=nobs(m),institutions=uniqueN(data$unitid),dropped=paste(m$collin.var,collapse=';'))
 },error=function(e){failures[[key]]<<-data.table(outcome=y,min_syllabi=floor,model=label,reason=conditionMessage(e))})
}

ridge=function(train,test,f,penalty){
 x=as.matrix(train[,..f]);xt=as.matrix(test[,..f]);mu=colMeans(x);sd=apply(x,2,sd);sd[sd<1e-10|!is.finite(sd)]=1
 x=cbind(1,sweep(sweep(x,2,mu),2,sd,'/'));xt=cbind(1,sweep(sweep(xt,2,mu),2,sd,'/'))
 sx=rowsum(x,as.character(train$pair),reorder=TRUE);sy=rowsum(train$delta1,as.character(train$pair),reorder=TRUE)[,1]
 nn=rowsum(rep(1,nrow(train)),as.character(train$pair),reorder=TRUE)[,1];den=nn+penalty
 beta=solve(crossprod(x)-crossprod(sx,sx/den)+diag(1e-8,ncol(x)),crossprod(x,train$delta1)-crossprod(sx,sy/den))
 a=(sy-as.numeric(sx%*%beta))/den
 as.numeric(xt%*%beta)+a[match(as.character(test$pair),rownames(sx))]
}

forecast=function(data,floor){
 data=copy(data)
 # Dummy features preserve field/activity baselines without future-year effects.
 dummy=model.matrix(~factor(field_id)+factor(skill_id),data=data)[,-1,drop=FALSE]
 if(ncol(dummy))for(j in seq_len(ncol(dummy)))data[,(paste0('dummy',j)):=dummy[,j]]
 base=c('lag_score','lag_score2','previous_change','previous_positive','previous_positive_over_peers',
        'log_previous','log_sources','source_mean','time',paste0('dummy',seq_len(ncol(dummy))))
 vt=data[year==2014];vv=data[year==2015 & pair %in% vt$pair]
 if(nrow(vt)<100||nrow(vv)<100||uniqueN(vt$unitid)<10)stop('Insufficient 2014–2015 chronological validation')
 candidates=c(3,10,30,100,1e6)
 errors=sapply(candidates,function(p)mean((vv$delta1-ridge(vt,vv,base,p))^2))
 penalty=candidates[which.min(errors)];penalties[[as.character(floor)]]<<-data.table(min_syllabi=floor,penalty=candidates,validation_mse=errors,chosen=candidates==penalty)
 train=data[year<=2015];ids=train[,.N,by=pair][N>=2,pair]
 train=train[pair %in% ids];test=data[year>=2016 & pair %in% ids]
 if(nrow(test)<100||uniqueN(test$unitid)<10)stop('Insufficient known-pair 2016–2017 test observations')
 specifications=list(baseline=base,direction=c(base,'direction_flow'),status=c(base,features),
                      placebo=c(base,paste0('placebo_',features)))
 predictions=lapply(specifications,function(f)ridge(train,test,f,penalty));base_error=(test$delta1-predictions$baseline)^2
 fields=fread(file.path(out,'fields.csv'))
 for(name in names(predictions)){
  tmp=test[,.(unitid,field_id)];tmp[,`:=`(sse=(test$delta1-predictions[[name]])^2,zero_sse=test$delta1^2,base_sse=base_error)]
  tmp=merge(tmp,fields,by='field_id')
  group=tmp[,.(n=.N,sse=sum(sse),zero_sse=sum(zero_sse),base_sse=sum(base_sse)),by=.(unitid,field)]
  all=tmp[,.(n=.N,sse=sum(sse),zero_sse=sum(zero_sse),base_sse=sum(base_sse)),by=unitid];all[,field:='All three fields']
  group=rbind(group,all);group[,`:=`(min_syllabi=floor,model=name)]
  losses[[paste(floor,name)]]<<-group
 }
}

for(floor in c(9L,20L)){
 sample=d[min_syllabi==floor]
 for(y in c('delta1','delta2')){
  sub=sample[is.finite(get(y))];ids=sub[,.N,by=pair][N>=2,pair];sub=sub[pair %in% ids]
  if(nrow(sub)<100||uniqueN(sub$unitid)<10){failures[[paste(y,floor)]]=data.table(outcome=y,min_syllabi=floor,model='association',reason='Insufficient repeated targets');next}
  fit(sub,y,'direction_flow','direction',floor)
  fit(sub,y,paste(features,collapse='+'),'status',floor)
  fit(sub,y,paste(paste0('placebo_',features),collapse='+'),'placebo',floor)
 }
 tryCatch(forecast(sample,floor),error=function(e){failures[[paste('forecast',floor)]]<<-data.table(outcome='delta1',min_syllabi=floor,model='forecast',reason=conditionMessage(e))})
}
if(length(coefs))fwrite(rbindlist(coefs),file.path(out,'coefficients.csv'))
if(length(influences))fwrite(rbindlist(influences),file.path(out,'influences.csv.gz'))
if(length(losses))fwrite(rbindlist(losses),file.path(out,'losses.csv.gz'))
if(length(failures))fwrite(rbindlist(failures),file.path(out,'failures.csv'))
if(length(diagnostics))fwrite(rbindlist(diagnostics),file.path(out,'model_diagnostics.csv'))
if(length(penalties))fwrite(rbindlist(penalties),file.path(out,'prediction_penalties.csv'))
if(!length(coefs))stop('No association model succeeded')
writeLines('{"complete":true}',file.path(out,'complete.json'))
