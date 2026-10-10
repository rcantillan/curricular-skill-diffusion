suppressPackageStartupMessages({library(data.table); library(fixest)})
setDTthreads(2L); setFixest_nthreads(2L)
args <- commandArgs(TRUE); stopifnot(length(args)==2)
tag <- args[1]; rootout <- args[2]
out <- file.path('outputs/content_channels',tag)
dt <- rbindlist(lapply(file.path('data/derived/content_channels',tag,paste0('panel_',2008:2017,'.csv.gz')),fread))
stopifnot(!anyDuplicated(dt,by=c('cell_id','skill_id','year')))
tax <- fread(file.path(rootout,'skill_taxonomy.csv'))
dt <- merge(dt,tax[,.(skill_id,onet_branch_id)],by='skill_id',all.x=TRUE)
dt[, `:=`(lag_score2=lag_score^2,log_n_previous=log(n_previous),log_n_current=log(n_current),
          log_n_inst=log1p(n_inst),log_n_field=log1p(n_field),time=year-2007)]
dt[, pair_id:=.GRP,by=.(cell_id,skill_id)]
scales <- fread(file.path(rootout,'global_scales.csv'))
for (v in scales$channel) {
  sc <- scales[channel==v]
  dt[,(paste0(v,'_std')):=if(is.finite(sc$sd) && sc$sd>1e-10) (get(v)-sc$mean)/sc$sd else NA_real_]
}
controls <- 'lag_score + lag_score2 + log_n_previous + log_n_current'
effects <- '| pair_id + skill_id^year + field_id^year + unitid^year'
strict <- '| pair_id + field_id^skill_id^year + unitid^year'
coefs <- list(); influences <- list(); failures <- list(); losses <- list(); tuning <- list()
fit <- function(d,y,rhs,fe,scope,label) {
  key <- paste(y,scope,label,sep='_')
  result <- tryCatch({
    m <- feols(as.formula(paste(y,'~',rhs,fe)),d,cluster=~unitid,fixef.rm='none',demeaned=TRUE,notes=FALSE)
    ct <- as.data.table(coeftable(m),keep.rownames='term'); setnames(ct,c('term','estimate','se','t','p'))
    ct <- ct[grepl('same_inst_std|same_field_std|hiring.*_std',term)]
    if (!nrow(ct)) stop('No channel coefficients estimable')
    # Retain the covariance induced by the same institutions across skill blocks.
    # fixest may retain removed collinear columns in X_demeaned. Use exactly
    # the estimated coefficients and its already computed inverse Hessian.
    x <- m$X_demeaned[,names(coef(m)),drop=FALSE]
    bread <- m$cov.unscaled/m$sigma2
    score <- rowsum(x*as.numeric(m$residuals),d$unitid,reorder=TRUE)
    inf <- score %*% bread; colnames(inf) <- names(coef(m))
    rawvar <- colSums(inf^2); adj <- diag(vcov(m))/rawvar
    finite_adj <- adj[is.finite(adj) & adj>0]
    stopifnot(length(finite_adj)>0)
    adjustment <- median(finite_adj)
    inf <- inf*sqrt(adjustment)
    reconstructed <- sqrt(colSums(inf[,ct$term,drop=FALSE]^2))
    stopifnot(max(abs(reconstructed-ct$se)/pmax(ct$se,1e-12)) < 1e-5)
    ct[, `:=`(outcome=y,scope=scope,model=label,rows=nobs(m))]
    ct[, supporting_institutions:=uniqueN(d$unitid)]
    if(scope=='discipline') {
      ct[,supporting_institutions:=vapply(term,function(t) {
        field <- as.integer(sub('field_id::([0-9]+):.*','\\1',t))
        uniqueN(d[field_id==field,unitid])
      },integer(1))]
    }
    if(scope=='onet') {
      ct[,supporting_institutions:=vapply(term,function(t) {
        branch <- sub('onet_branch_id::([^:]+):.*','\\1',t)
        uniqueN(d[onet_branch_id==branch,unitid])
      },integer(1))]
    }
    coefs[[key]] <<- ct
    ii <- as.data.table(inf[,ct$term,drop=FALSE]); ii[,unitid:=as.integer(rownames(inf))]
    ii <- melt(ii,id.vars='unitid',variable.name='term',value.name='influence')
    ii[,`:=`(outcome=y,scope=scope,model=label)]
    influences[[key]] <<- ii
    invisible(m)
  },error=function(e) {
    failures[[key]] <<- data.table(outcome=y,scope=scope,model=label,reason=conditionMessage(e)); NULL
  })
  invisible(result)
}

# Shrink program-skill intercepts; select penalty using ONLY 2012–2013 validation.
ridge_predict <- function(train,test,y,features,penalty) {
  x <- as.matrix(train[,..features]); xt <- as.matrix(test[,..features])
  mu <- colMeans(x); sd <- apply(x,2,sd); sd[!is.finite(sd)|sd<1e-10] <- 1
  x <- cbind(intercept=1,sweep(sweep(x,2,mu),2,sd,'/'))
  xt <- cbind(intercept=1,sweep(sweep(xt,2,mu),2,sd,'/'))
  ids <- as.character(train$pair_id); yt <- train[[y]]
  sx <- rowsum(x,ids,reorder=TRUE); sy <- rowsum(yt,ids,reorder=TRUE)[,1]
  nn <- rowsum(rep(1,nrow(train)),ids,reorder=TRUE)[,1]; den <- nn+penalty
  a <- crossprod(x)-crossprod(sx,sx/den)
  b <- crossprod(x,yt)-crossprod(sx,sy/den)
  beta <- solve(a+diag(1e-8,ncol(x)),b)
  intercept <- (sy-as.numeric(sx%*%beta))/den
  as.numeric(xt%*%beta)+intercept[match(as.character(test$pair_id),rownames(sx))]
}
forecast <- function(d,y) {
  d <- copy(d)
  d[, endpoint:=year+as.integer(y=='delta2')]
  features <- c('lag_score','lag_score2','log_n_previous','log_n_inst','log_n_field','time')
  vt <- d[endpoint<=2011]; vv <- d[year>=2012 & endpoint<=2013]
  ids <- vt[,.N,by=pair_id][N>=2,pair_id]; vt <- vt[pair_id %in% ids]; vv <- vv[pair_id %in% ids]
  penalties <- c(0,3,10,30,100,1e6)
  if(nrow(vt)<100 || nrow(vv)<100) stop('Insufficient chronological validation observations')
  errors <- sapply(penalties,function(p) mean((vv[[y]]-ridge_predict(vt,vv,y,features,p))^2))
  penalty <- penalties[which.min(errors)]
  tuning[[y]] <<- data.table(outcome=y,penalty=penalties,validation_mse=errors,chosen=penalties==penalty)
  train <- d[endpoint<=2013]; test <- d[year>2013]
  ids <- train[,.N,by=pair_id][N>=3,pair_id]; train <- train[pair_id %in% ids]; test <- test[pair_id %in% ids]
  if(nrow(train)<100 || nrow(test)<100) stop('Insufficient held-out observations')
  specs <- list(baseline=features,institution=c(features,'same_inst_std'),
                discipline=c(features,'same_field_std'),both=c(features,'same_inst_std','same_field_std'))
  preds <- lapply(specs,function(f) ridge_predict(train,test,y,f,penalty))
  base <- (test[[y]]-preds$baseline)^2
  for(name in names(preds)) {
    temp <- test[,.(unitid,field_id,onet_branch_id)]
    temp[,`:=`(sse=(test[[y]]-preds[[name]])^2,sae=abs(test[[y]]-preds[[name]]),
               zero_sse=test[[y]]^2,base_sse=base)]
    for(dimension in c('all','field_id','onet_branch_id')) {
      temp[,category:=if(dimension=='all') 'all' else as.character(get(dimension))]
      tab <- temp[,.(n=.N,sse=sum(sse),sae=sum(sae),zero_sse=sum(zero_sse),base_sse=sum(base_sse)),by=.(unitid,category)]
      tab[,`:=`(outcome=y,dimension=dimension,model=name)]
      losses[[paste(y,name,dimension)]] <<- tab
    }
  }
}
for(y in c('delta1','delta2')) {
  cov <- if(y=='delta1') 'coverage1' else 'coverage2'
  d <- dt[get(cov)>=9 & is.finite(get(y)) & is.finite(same_inst_std) & is.finite(same_field_std)]
  ids <- d[,.N,by=pair_id][N>=2,pair_id]; d <- d[pair_id %in% ids]
  fit(d,y,paste(controls,'+ same_inst_std + same_field_std'),effects,'pooled','both')
  fit(d,y,paste(controls,'+ same_inst_std'),strict,'pooled','strict_internal')
  fit(d,y,paste(controls,'+ i(field_id,same_inst_std) + i(field_id,same_field_std)'),effects,'discipline','both')
  fit(d,y,paste(controls,'+ i(field_id,same_inst_std)'),strict,'discipline','strict_internal')
  fit(d,y,paste(controls,'+ i(onet_branch_id,same_inst_std) + i(onet_branch_id,same_field_std)'),effects,'onet','both')
  fit(d,y,paste(controls,'+ i(onet_branch_id,same_inst_std)'),strict,'onet','strict_internal')
  for(h in c('hiring2015','hiring2022')) {
    hd <- d[is.finite(get(paste0(h,'_std'))) & get(paste0('n_',h))>=2 & get(paste0('share_',h))>=.5]
    ids <- hd[,.N,by=pair_id][N>=2,pair_id]; hd <- hd[pair_id %in% ids]
    if(nrow(hd)>100 && uniqueN(hd$unitid)>=10) {
      fit(hd,y,paste(controls,'+ same_inst_std + same_field_std'),effects,h,'both')
      fit(hd,y,paste(controls,'+ same_inst_std + same_field_std +',paste0(h,'_std')),effects,h,'both_plus_hiring')
    } else failures[[paste(y,h)]] <- data.table(outcome=y,scope=h,model='hiring',reason='Insufficient coverage')
  }
  tryCatch(forecast(d,y),error=function(e) {
    failures[[paste(y,'forecast')]] <<- data.table(outcome=y,scope='forecast',model='ridge',reason=conditionMessage(e))
  })
}
if(length(coefs)) fwrite(rbindlist(coefs),file.path(out,'block_coefficients.csv'))
if(length(influences)) fwrite(rbindlist(influences),file.path(out,'cluster_influences.csv.gz'))
if(length(losses)) fwrite(rbindlist(losses),file.path(out,'forecast_losses.csv.gz'))
if(length(tuning)) fwrite(rbindlist(tuning),file.path(out,'forecast_penalties.csv'))
if(length(failures)) fwrite(rbindlist(failures),file.path(out,'block_failures.csv'))
if(!length(coefs)) stop('No model succeeded; inspect block_failures.csv')
writeLines('{"complete":true}',file.path(out,'block_complete.json'))
