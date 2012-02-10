 read.ma <- function(out,include=NULL,hl=NULL){

          ma.name <- out$input$ma.name

      out.list <- out$dat$ma
      if(file.access(ma.name,mode=0)!=0) stop(paste("input file supplied", ma.name, "does not exist",sep=" "))

          try(ma<-read.csv(ma.name,skip=2))
          if(is.null(hl)){
          hl<-readLines(ma.name,1)
          hl=strsplit(hl,',')
          }
          colnames(ma) = hl[[1]]

          tif.info<-readLines(ma.name,3)
          tif.info<-strsplit(tif.info,',')
          temp<-tif.info[[2]]
          temp[1:3]<-0
          if(is.null(include)) include<-as.numeric(temp)

          paths<-as.character(tif.info[[3]])

      if(class(ma)=="try-error") stop("Error reading MDS")

          #reading some info on the other steps in the workflow to be used in
          #appended output
              temp<-strsplit(tif.info[[2]][1],split="\\\\")[[1]]
            out.list$input$FieldDataTemp<-temp[length(temp)]

                temp<-strsplit(tif.info[[2]][2],split="\\\\")[[1]]
            out.list$input$OrigFieldData<-temp[length(temp)]

               temp<-strsplit(tif.info[[2]][3],split="\\\\")[[1]]
            out.list$input$CovSelectName<-temp[length(temp)]

                temp<-strsplit(tif.info[[3]][1],split="\\\\")[[1]]
            out.list$input$ParcTemplate<-temp[length(temp)]

            temp<-strsplit(tif.info[[3]][2],split="\\\\")[[1]]
            out.list$input$ParcOutputFolder<-temp[length(temp)]

            temp<-strsplit(tif.info[[2]][2],split="\\\\")[[1]]
            out.list$input$OrigFieldData<-temp[length(temp)]

          r.name <- out$input$response.col
          if(r.name=="responseCount") out$input$model.family="poisson"

      r.col <- grep(r.name,names(ma))
      if(length(r.col)==0) stop("Response column was not found")
      if(length(r.col)>1) stop("Multiple columns matched the response column")
      names(ma)[r.col]<-"response"
      rm.list<-vector()

        # remove background points which aren't used here
         if(length(which(ma[,r.col]==-9999,arr.ind=TRUE))>0) ma<-ma[-c(which(ma[,r.col]==-9999,arr.ind=TRUE)),]
        # remove evaluation points
        if(any(!is.na(match("EvalSplit",names(ma))))){
             EvalIndx<-match("EvalSplit",names(ma))
             ma<-ma[-c(which(ma[,EvalIndx]=="test",arr.ind=TRUE)),]
             rm.list<-EvalIndx
        }



      # find and save xy columns#
      xy.cols <- na.omit(c(match("x",tolower(names(ma))),match("y",tolower(names(ma)))))
      if(length(xy.cols)>0)  rm.list<-c(rm.list,xy.cols)

       # remove weight column except for Random Forest
       site.weights<-c(match("weights",tolower(names(ma))),c(match("site.weights",tolower(names(ma)))))
        if(any(!is.na(site.weights))) {rm.list<-c(rm.list,na.omit(site.weights))
            if(out$input$script.name=="rf") ma[,na.omit(site.weights)]<-rep(1,times=dim(ma)[1])
            site.weights=na.omit(site.weights)
        }
        else{ ma$weights=rep(1,times=dim(ma)[1])
          rm.list<-c(rm.list,ncol(ma))
           site.weights=ncol(ma)
        }
        # and index as well
       split.indx<-match("split",tolower(names(ma)))
        if(length(na.omit(split.indx))>0) rm.list<-c(rm.list,split.indx)

       #complete the list of columns to include
          include[is.na(include)]<-0
          rm.list<-c(rm.list,(which(include!=1,arr.ind=TRUE)))
          rm.list<-unique(rm.list[!is.na(rm.list)])
          
      ######################### REMOVING INCOMPLETE CASES ###############
        #remove incomplete cases but only for include variables
       all.cases<-nrow(ma)
          ma[ma==-9999]<-NA
          ma<-ma[complete.cases(ma[,-c(rm.list)]),]
          comp.cases<-nrow(ma)
          if(comp.cases/all.cases<.9) warning(paste(round((1-comp.cases/all.cases)*100,digits=2),"% of cases were removed because of missing values",sep=""))
      #########################################################################
        #split out the weights,response, and xy.columns after removing incomplete cases

        
      ma.names<-names(ma)
      # tagging factors and looking at their levels
         factor.cols <- grep("categorical",names(ma))
      factor.cols <- factor.cols[!is.na(factor.cols)]
      out.list$bad.factor.cols=NULL
      if(length(factor.cols)==0){
          out.list$factor.levels <- NA
          } else {
                names(ma) <- ma.names <-  sub("_categorical","",ma.names)
                factor.names <- ma.names[factor.cols]
                factor.levels <- list()
                for (i in 1:length(factor.cols)){
                 f.col <- factor.cols[i]

                        x <- table(ma[,f.col])
                        if(nrow(x)<2){
                              out.list$bad.factor.cols <- c(out.list$bad.factor.cols,factor.names[i])
                              }
                        if(any(x<10)) warning(paste("Some levels for the categorical predictor ",names(dat)[factor.cols[i]]," do not have at least 10 observations.\n",
                                                                   "you might want to consider removing or reclassifying this predictor before continuing.\n",
                                                                   "Factors with few observations can cause failure in model fitting when the data is split and cannot be reilably used in training a model.",sep=""))
                        lc.levs <-  as.numeric(row.names(x))[x>0] # make sure there is at least one "available" observation at each level
                        lc.levs <- data.frame(number=lc.levs,class=lc.levs)
                        factor.levels[[i]] <- lc.levs

                    ma[,f.col] <- factor(ma[,f.col],levels=lc.levs$number,labels=lc.levs$class)
                    }

                    names(factor.levels)<-factor.names
                    out.list$factor.levels <- factor.levels

                if(!is.null(out.list$bad.factor.cols)) rm.list<-c(rm.list,match(out.list$bad.factor.cols,names(ma)))
          }

            #removing predictors with only one unique value
            if(length(which(lapply(apply(ma[,-c(rm.list)],2,unique),length)==1,arr.ind=TRUE))>0){
                warning(paste("\nThe Following Predictors will be removed because they have only 1 unique value: ",
                names(which(lapply(apply(ma[,-c(rm.list)],2,unique),length)==1,arr.ind=TRUE)),sep=" "))
                rm.list<-c(rm.list,which(lapply(apply(ma,2,unique),length)==1,arr.ind=TRUE))
                }

                rm.list<-rm.list[rm.list!=r.col]
                  #splitting the data into test and training splits (should work for CV splits as well and then splits the dataframe into data/response $dat
                  #$XY and $weights
                   if(length(na.omit(split.indx))>0){ dat.out<-split(ma,f=ma[,split.indx],drop=TRUE)
                   if(all(c("test","train")%in%names(table(ma[split.indx])))) Split.type="test"
                        else Split.type="crossValidation"
                   }
                   else{ dat.out=list(train=ma)
                     Split.type="none"
                   }
                   selector<-ma$Split
                   if(Split.type=="crossValidation") dat.out$train<-ma
                   #Removing everything in the remove list here and setting up the structure for output
                     for(i in 1:length(dat.out)){
                        dat.out[[i]]<-list(resp=dat.out[[i]][r.col],XY=dat.out[[i]][,xy.cols],dat=dat.out[[i]][,-c(rm.list)],weight=dat.out[[i]][,site.weights])
                        names(dat.out[[i]]$XY)<-toupper(names(dat.out[[i]]$XY))
                     }
                     if(nrow(dat.out$train$dat)/(ncol(dat.out$train$dat)-1)<3) stop("You have less than 3 observations for every predictor\n consider reducing the number of predictors before continuing")

                   temp.fct<-function(l){table(l$resp)}
                out.list$nPresAbs<-lapply(dat.out,temp.fct)
          
      # check that response column contains only 1's and 0's, but not all 1's or all 0's if GLMFamily==binomial
      if(out$input$response.col=="responseCount") out$input$model.family<-"poisson"
        else out$input$model.family="binomial"

      if(tolower(out$input$model.family)=="bernoulli" || tolower(out$input$model.family)=="binomial"){
           if((Split.type=="crossValidation" & any(names(apply(do.call("rbind",out.list$nPresAbs),2,sum))!=c("0","1"))) |
          (Split.type!="crossValidation" & !any(match(as.numeric(names(out.list$nPresAbs$train)),c(0,1))==(c(1,2)))))
          stop("response column (#",r.col,") in ",ma.name," is not binary 0/1 for the training split",sep="")
          }

  #check that response column contains at least two unique values for counts

      if(tolower(out$input$model.family)=="poisson"){
          if(length(out.list$nPresAbs$train)==1)
          stop("response column (#",r.col,") in ",ma.name," does not have at least two unique values in the train split",sep="")
          }

                    paths<-paths[-c(r.col,rm.list)]
                    include<-include[-c(r.col,rm.list)]
                    
         ma.names<-names(ma)

      # if producing geotiff output, check to make sure geotiffs are available for each column of the model array #
        if(out$input$make.binary.tif==T | out$input$make.p.tif==T){
                #Check that tiffs to be used exist
         if(sum(file.access(paths),mode=0)!=0){
                         temp<-as.vector(file.access(paths))==-1
                         temp.paths<-paths[temp]
                  stop("the following geotiff(s) are missing:",
                      "\nif these are intentionally left blank, uncheck makeBinMap and makeProbabilityMap options\n",
                        paste(paths[temp],collapse="\n"),sep="")
                          }

                 } else out.list$tif.names <- ma.names[-1]

                 out.list$tif.ind<-paths

        out.list$dims <- sum(out.list$nPresAbs$train)

        out.list$used.covs <-  names(dat.out$train$dat)[-1]

      if(out$input$script.name%in%c("brt","rf")){
      #brt uses a subsample for quicker estimation of learning rate and model simplificaiton
      #random forest uses a subsample only for producing response curves
      samp.size<-ifelse(out$input$script.name=="brt",500,50)
       model.fitting.subset=c(n.pres=samp.size,n.abs=samp.size)
        out.list$Subset$ratio <- min(sum(model.fitting.subset)/out.list$dims[1],1)
            pres.sample <- sample(c(1:nrow(dat.out$train$dat))[dat.out$train$dat[,1]>=1],min(out.list$nPresAbs$train[2],out$input$model.fitting.subset[1]))
            abs.sample <- sample(c(1:nrow(dat.out$train$dat))[dat.out$train$dat[,1]==0],min(out.list$nPresAbs$train[1],out$input$model.fitting.subset[2]))
            out.list$Subset$dat <- dat.out$train$dat[c(pres.sample,abs.sample),]
            out.list$Subset$weight<-dat.out$train$weight[c(pres.sample,abs.sample)]
            out.list$Subset$nPresAbs <-table(dat.out$train$dat[1,])
            }
              if(Split.type=="crossValidation") out.list$selector=selector
              out.list$split.type=Split.type
              out.list$ma<-dat.out
          out$dat <- out.list

return(out)
}