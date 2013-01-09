parRaster<-function(start.tile,dims,tr,MESS,nvars,fullnames,nvars.final,vnames,NAval,
factor.levels,model,Model,pred.fct,make.binary.tif,RasterInfo,outfile.p,outfile.bin,thresh,nToDo,ScriptPath,vnames.final.mod,train.dat,residSmooth) {
    #loading code and libraries that are needed
    setwd(file.path(ScriptPath))
    source("pred.fct.r")
    source("chk.libs.r")
    source("CalcMESSSuperNew.r")
    if(!is.null(residSmooth)) source("Pred.Surface.r")
    source(paste(toupper(Model),".helper.fcts.r",sep=""))
   
    chk.libs(Model)
    options(warn=-1)
     on.exit(options(warn=0))
    #for the last set we have to adjust tr$n based on the number of remaining tiles
    if((start.tile+nToDo)>tr$n) nToDo=tr$n-start.tile+1
    #have to hack in to change the extent for writting sections to seperate files because crop crashes for large files
    start.val<-xyFromCell(RasterInfo,cellFromRowCol(RasterInfo, rownr=ifelse((start.tile+nToDo)>tr$n,nrow(RasterInfo),(tr$row[(start.tile+nToDo)]-1)), 
            colnr=1))-.5*res(RasterInfo)[2]
    end.val<-xyFromCell(RasterInfo,cellFromRowCol(RasterInfo, rownr=tr$row[start.tile], colnr=ncol(RasterInfo))) +.5*res(RasterInfo)[2]
    RasterInfo@extent@ymin<-start.val[1,2]
    RasterInfo@extent@ymax<-end.val[1,2]
    RasterInfo@nrows=as.integer(sum(tr$nrows[start.tile:(start.tile+nToDo-1)]))
  
   continuousRaster<-raster(RasterInfo)
   outfile.p<-file.path(paste(substr(outfile.p,1,(nchar(outfile.p)-4)),ifelse(start.tile==1,"",start.tile),".tif",sep=""))
   outtext<-paste(substr(outfile.p,1,(nchar(outfile.p)-4)),start.tile,".txt",sep="")
   capture.output(cat(paste(nToDo,"tiles to do\n")),file=outtext,append=TRUE)
   if(make.binary.tif) outfile.bin<-(sub("ProbTiff","BinTiff",sub("prob","bin",outfile.p))) 
    #start up any rasters we need   
    continuousRaster <- writeStart(continuousRaster, filename=outfile.p, overwrite=TRUE)
    if(make.binary.tif) {
      binaryRaster<-raster(RasterInfo)
      binaryRaster <- writeStart(binaryRaster, filename=outfile.bin, overwrite=TRUE)}
    if(MESS) {
      MessRaster<-raster(RasterInfo)
      ModRaster<-raster(RasterInfo)
      MessRaster <- writeStart(MessRaster, filename=sub("ProbTiff","MESSTiff",sub("prob","mess",outfile.p)), overwrite=TRUE)
      ModRaster <- writeStart(ModRaster, filename=sub("ProbTiff","ModTiff",sub("prob","MoD",outfile.p)), overwrite=TRUE)
        train.dat<-train.dat[,match(vnames.final.mod,names(train.dat))]
        for(k in 1:nvars.final) train.dat[,k]<-sort(train.dat[,k])
    }
     
 for (i in start.tile:min(start.tile+nToDo-1,length(tr$row))){
   capture.output(cat(paste("starting tile", i,Sys.time(),"\n")),file=outtext,append=TRUE)
   #alter the write start location because we always start at position 1                                   
   writeLoc<-ifelse((start.tile-1)==0,tr$row[i],tr$row[i]-sum(tr$nrows[1:(start.tile-1)]))
       temp <- data.frame(matrix(ncol=nvars.final,nrow=tr$nrows[i]*dims[2]))
       names(temp) <- vnames.final.mod
       # fill temp data frame 
       browser()        
    for(k in 1:nvars.final) 
         temp[,k]<- getValuesBlock(raster(fullnames[match(vnames.final.mod[k],vnames)]), row=tr$row[i], nrows=tr$nrows[i])
     if(MESS){
         pred.rng<-rep(NA,nrow(temp))
         pred.rng[complete.cases(temp)]<-CalcMESS(temp[complete.cases(temp),],train.dat=train.dat)
         names(pred.rng)[names(pred.rng)==""]<-NA
     }
   if(length(vnames)==1) names(temp)=vnames
   temp[temp==NAval] <- NA # replace missing values #
        if(sum(!is.na(factor.levels))){
            factor.cols <- match(names(factor.levels),names(temp))
            if(sum(!is.na(factor.cols))>0){
            for(j in 1:length(factor.cols)){
                if(!is.na(factor.cols[j])){
                    temp[,factor.cols[j]] <- factor(temp[,factor.cols[j]],levels=factor.levels[[j]]$number,labels=factor.levels[[j]]$class)
                }
            }
                   }}
      ifelse(sum(complete.cases(temp))==0,  # does not calculate predictions if all predictors in the region are na
        preds<-matrix(data=NA,nrow=dims[2],ncol=tr$nrows[i]),
        preds <- t(matrix(pred.fct(model,temp,Model),ncol=dims[2],byrow=T)))
      
        preds[is.na(preds)]<-NAval
        
        if(MESS) {
          MessRaster<-writeValues(MessRaster,pred.rng, writeLoc)
          ModRaster<-writeValues(ModRaster,names(pred.rng), writeLoc)
        }
          if(make.binary.tif) binaryRaster<-writeValues(binaryRaster,(preds>thresh),writeLoc)
       continuousRaster <- writeValues(continuousRaster,preds,writeLoc)
   } #end of the big for loop

   end.seq<-c(tr$row,dims[1]+1)
  
   continuousRaster <- writeStop(continuousRaster)
  
  if(make.binary.tif) {
    writeStop(binaryRaster)
  }
  if(MESS) {
    writeStop(MessRaster)
    writeStop(ModRaster)
      #I need to uncomment this later but for now I'd like it not to break
    #  d<-data.frame(as.integer(seq(1:ncol(pred.rng))),names(pred.rng))
     # names(d)=c("Value","Class")
    #  ModRaster@file@datanotation<-"INT1U"
    #  write.dbf(d, sub(".tif",".tif.vat.dbf",ModRaster@file@name), factor2char = TRUE, max_nchar = 254)

  }

 if(!is.null(residSmooth)) Pred.Surface(object=raster(outfile.p),model=residSmooth,filename=(sub("ProbTiff","ResidTiff",sub("prob","resid",outfile.p))),NAval=NAval)
}
