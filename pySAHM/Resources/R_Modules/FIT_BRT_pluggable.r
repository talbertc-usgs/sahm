make.p.tif=T
make.binary.tif=T

tc=NULL
n.folds=3
alpha=1

learning.rate = NULL
bag.fraction = 0.5
prev.stratify = TRUE
max.trees = 10000
tolerance.method = "auto"
tolerance = 0.001
seed=NULL
opt.methods=2
save.model=TRUE
MESS=FALSE
# Interpret command line argurments #
# Make Function Call #
Args <- commandArgs(trailingOnly=FALSE)

    for (i in 1:length(Args)){
     if(Args[i]=="-f") ScriptPath<-Args[i+1]
     }

    for (arg in Args) {
    	argSplit <- strsplit(arg, "=")
    	argSplit[[1]][1]
    	argSplit[[1]][2]
    	if(argSplit[[1]][1]=="c") csv <- argSplit[[1]][2]
    	if(argSplit[[1]][1]=="o") output <- argSplit[[1]][2]
    	if(argSplit[[1]][1]=="rc") responseCol <- argSplit[[1]][2]
   		if(argSplit[[1]][1]=="mpt") make.p.tif <- argSplit[[1]][2]
 			if(argSplit[[1]][1]=="mbt")  make.binary.tif <- argSplit[[1]][2]
      if(argSplit[[1]][1]=="tc")  tc <- argSplit[[1]][2]
 			if(argSplit[[1]][1]=="nf")  n.folds <- argSplit[[1]][2]
 			if(argSplit[[1]][1]=="alp")  alpha <- argSplit[[1]][2]
      if(argSplit[[1]][1]=="lr")  learning.rate <- argSplit[[1]][2]
 			if(argSplit[[1]][1]=="bf")  bag.fraction <- argSplit[[1]][2]
 			if(argSplit[[1]][1]=="ps")  prev.stratify <- argSplit[[1]][2]
 			if(argSplit[[1]][1]=="mt")  max.trees <- argSplit[[1]][2]
 			if(argSplit[[1]][1]=="om")  opt.methods <- argSplit[[1]][2]
 			if(argSplit[[1]][1]=="seed")  seed <- argSplit[[1]][2]
 		  if(argSplit[[1]][1]=="savm")  save.model <- argSplit[[1]][2]
 		  if(argSplit[[1]][1]=="tolm")  tolerance.method <- argSplit[[1]][2]
 		  if(argSplit[[1]][1]=="tol")  tolerance <- argSplit[[1]][2]
 		  if(argSplit[[1]][1]=="mes")  MESS <- argSplit[[1]][2]
 			
    }
	print(csv)
	print(output)
	print(responseCol)

ScriptPath<-dirname(ScriptPath)
source(paste(ScriptPath,"LoadRequiredCode.r",sep="\\"))


alpha<-as.numeric(alpha)
make.p.tif<-as.logical(make.p.tif)
make.binary.tif<-as.logical(make.binary.tif)
prev.stratify<-as.logical(prev.stratify)
save.model<-make.p.tif | make.binary.tif
opt.methods<-as.numeric(opt.methods)
MESS<-as.logical(MESS)
print(getwd())
print(ScriptPath)
    fit.brt.fct(ma.name=csv,
		tif.dir=NULL,
		output.dir=output,
		response.col=responseCol,
		make.p.tif=make.p.tif,make.binary.tif=make.binary.tif,
		simp.method="cross-validation",debug.mode=F,responseCurveForm="pdf",tc=tc,n.folds=n.folds,alpha=alpha,script.name="brt",
		learning.rate =learning.rate, bag.fraction = bag.fraction,prev.stratify = prev.stratify,max.trees = max.trees,seed=seed,
    save.model=save.model,opt.methods=opt.methods,MESS=MESS)



