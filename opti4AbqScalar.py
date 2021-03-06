import os
import toolbox
import subprocess

verbose = False
saveIntermediateValues = True
NFeval = 0
NIter = 0

def computeFEData(p,modelsDir):
    files = os.listdir(modelsDir)
    files.sort()
    '''
    populates a list of model names found in modelsDir and a list of model outputs after they have run with parameter p
    '''
    modelList = list()
    for modelScript in files:
        if (modelScript.endswith('.py')) and ('__init__' not in modelScript):
            modelList.append(modelScript)
    else:#no break
        output = list()
        for model in modelList:
            out1job = runModel(p,model,modelsDir)
            output.append(out1job[0])
    return output,modelList

def runModel(p,modelScript,modelsDir):
    '''
    run abaqus models:
    1/ create a working directory for abaqus (in workspace\name_of_modelsDir_from_common_path_with_current_directory)
    2/ runs an abaqus cae analysis in the working directory (all abaqus files written in that directory): abaqus cae noGUI=path_to_modelScript -- p
    3/ runs an abaqus post-processing analysis by looking for the postPro function defined in the modelScript with argument the odb file of the previously run model
    '''
    #1/ create working directory
    baseName = os.getcwd()#os.path.dirname(os.path.abspath(__file__))
    import sys
    if baseName not in sys.path:sys.path.append(baseName)
    filePath = os.path.join(modelsDir,modelScript)
    workspace = toolbox.getWorkspace(filePath,baseName=baseName)
    if not(os.path.isdir(workspace)):
        try: os.makedirs(workspace)
        except WindowsError: print("file(s) probably locked!\n")
    # run abaqus analysis (function of parameters p) in workspace
    os.chdir(workspace)
    #2/ runs abaqus cae
    if verbose: print "running abaqus cae on %s"%(toolbox.getFileName(filePath))
    cmd = 'abaqus cae noGUI=%s'%(filePath)
    paramString = str(p)
    cmd += ' -- %s > %s 2>&1'%(paramString,'exeCalls.txt')
    if verbose: print 'cmd= ',cmd
    pCall1 = subprocess.call(cmd, shell=True)
    os.chdir(baseName)
    #3/ run abaqus postPro -- needs to be called with abaqus python as abaqus-specific modules are needed!!
    # solution: run in a new subprocess the file runPostPro.py called with the appropriate modelScript and working directory
    cmd = 'abaqus python runPostPro.py %s %s'%(filePath,workspace)
    pCall2 = subprocess.call(cmd, shell=True)
    if pCall2:#the post pro function has not run properly --> writes an error file
        writeErrorFile(workspace,modelScript,p,pCall1,pCall2)
        raise Exception("!! something has gone wrong, check notRun.txt")
    else:# reads the written output of the post-processing function as a float
        feOutputFile = os.path.join(workspace,'output.ascii')#could be generalised to allow the user to input a fileName!
        with open(feOutputFile, 'r') as file:   
            output = zip(*(map(float,line.split()) for line in file))
        return output

def writeErrorFile(workspace,modelScript,p,pCall1,pCall2='not run yet'):
    feErrorFile = os.path.join(workspace,'notRun.txt')
    global NFeval
    with open(feErrorFile, 'w') as file:
        file.write('running abaqus cae on %s returned %s\n'%(toolbox.getFileName(modelScript), pCall1))
        file.write('running post pro on %s returned %s\n'%(toolbox.getFileName(modelScript), pCall2))
        file.write('parameter inputs: %s\n'%(p))
        file.write('run number: %s\n'%(NFeval))

def plotValues(fittedValues, modelScript, expData):
    baseName = os.path.dirname(os.path.abspath(__file__))
    workspace = toolbox.getWorkspace(modelScript,baseName)
    os.chdir(workspace)
    figFilePng = os.path.join(workspace,'fittedResults2.png')
    figFilePdf = os.path.join(workspace,'fittedResults2.pdf')
    import matplotlib.pyplot as plt
    plt.plot(expData[0],expData[1],'o',fittedValues[0],fittedValues[1],'x')
    plt.legend(['Data', 'Fit'])
    plt.title('Least-squares fit to data')
    plt.savefig(figFilePng, bbox_inches='tight')
    plt.savefig(figFilePdf, bbox_inches='tight')
    if not verbose:plt.show()
    return fittedValues

def saveValues(p, feData, value, no='final'):
    baseName = os.path.dirname(os.path.abspath(__file__))
    feDataFile = os.path.join(baseName,'verboseValues_%i.ascii'%no)
    with open(feDataFile, 'w') as file:
        file.write('run number: %s\n'%(no))
        file.write('parameter inputs: %s\n'%(p))
        file.write('least square error %s\n'%value)
        file.write('\n'.join('%f ' %(x[0]) for x in feData))

def residuals(p, modelsDir, expDir):
    ''' residuals(p, modelsDir, expDir) computes the diff (in a least square sense) between experimental data and FE data (function of p)
        p: parameter to optimize
        modelsDir: directory with the computational models, contains python scripts defining and running the FE model. Each script must also contain a function called postPro
        expDir: directory with experimental data to fit, should contains ascii files whose names are the same as the FE model names
    each ascii file is contains one value (the experimental equivalent of the FE output value)
    '''
    feData,modelNames = computeFEData(p,modelsDir)
    #
    import numpy as np
    diff = list()
    for data,name in zip(feData,modelNames):
        #read data file
        dataFile = os.path.join(expDir,name.split('.')[0]+'.ascii')
        with open(dataFile, 'r') as file: expData =  float(file.readline().split()[0])
        # add difference in list
        if data[0]: diff.append((expData - data[0])/expData)
    lstSq = 0
    for value in diff: lstSq+= value**2/(len(diff))
    global NFeval
    NFeval += 1
    if saveIntermediateValues: saveValues(p, feData, lstSq, NFeval)
    return lstSq    

# def callbackF(p):
    # global NIter,NFeval
    # NIter += 1
    # if verbose: print 'Nb Iteration: %i, Nb Evaluation: %i, parameter inputs: %s\n'%(NIter,NFeval,p)
    # baseName = os.path.dirname(os.path.abspath(__file__))
    # callbackFile = os.path.join(baseName,'callbackValues_%i.ascii'%NIter)
    # with open(callbackFile, 'w') as file:
        # file.write('iteration number: %i\n'%(NIter))
        # file.write('evaluation number: %i\n'%(NFeval))
        # file.write('parameter inputs: %s\n'%(p))

def getOptiParam(modelsDir, expDir, optiParam, pBounds=None):
    from scipy.optimize import minimize_scalar
    opts = {'maxiter':optiParam['maxEval'],'disp':True}
    import numpy as np
    res = minimize_scalar(residuals, bounds=pBounds, args=(modelsDir, expDir), tol=optiParam['ftol'], method='bounded')#, options=opts)
    # pLSQ = res.x
    # fVal = res.fun
    # d = {}
    # d['funcalls']= res.nfev
    # d['task']= res.message
    if verbose: print res.message
    return res.x,res.fun,res.nfev,res.message

def main(expDir, modelsDir, options={}, pBounds=None):
    optiParam = {}
    optiParam['maxEval']=10
    optiParam['ftol']=1e-8
    optiParam.update(options)
    return getOptiParam(modelsDir, expDir, optiParam, pBounds)