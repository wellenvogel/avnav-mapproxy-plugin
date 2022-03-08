###############################################################################
# Copyright (c) 2021, Andreas Vogel andreas@wellenvogel.net
#
#  Permission is hereby granted, free of charge, to any person obtaining a
#  copy of this software and associated documentation files (the "Software"),
#  to deal in the Software without restriction, including without limitation
#  the rights to use, copy, modify, merge, publish, distribute, sublicense,
#  and/or sell copies of the Software, and to permit persons to whom the
#  Software is furnished to do so, subject to the following conditions:
#
#  The above copyright notice and this permission notice shall be included
#  in all copies or substantial portions of the Software.
#
#  THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
#  OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
#  FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
#  THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
#  LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
#  FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
#  DEALINGS IN THE SOFTWARE.
###############################################################################
import datetime
import importlib.util
import os
import signal
import subprocess
import sys
import threading
import time

import yaml

def loadModuleFromFile(fileName):
  if not os.path.isabs(fileName):
    fileName=os.path.join(os.path.dirname(__file__),fileName)
  moduleName=os.path.splitext(os.path.basename(fileName))[0]
  # see https://docs.python.org/3/library/importlib.html#module-importlib
  spec = importlib.util.spec_from_file_location(moduleName, fileName)
  module = importlib.util.module_from_spec(spec)
  spec.loader.exec_module(module)
  sys.modules[moduleName] = module
  return module

class OtherRunningException(Exception):
  def __init__(self):
    super().__init__('another seed is already running')
class PausedException(Exception):
  def __init__(self):
    super().__init__('cannot start a new seed while paused')

injector=loadModuleFromFile('injector.py')

ENV_PID='AVNAV_PARENT_PID'
class SeedRunner(object):
  STATE_RUNNING="running"
  STATE_OK="ok"
  STATE_ERROR="error"
  STATE_INACTIVE="inactive"
  CURRENT_CONFIG="seed.yaml"
  LAST_CONFIG="last_seed.yaml"
  PROGRESS_FILE="progress"
  LOGFILE="seed.log"
  INFOFILE="info.yaml"
  def __init__(self,workdir,configFile,configDirs,logHandler=None,keepLogs=20):
    self.workdir=workdir
    if not os.path.isdir(workdir):
      raise Exception("workdir %s does not exist"%workdir)
    self.keepLogs=keepLogs
    self.child=None
    self.configFile=configFile
    self.currentlyStarting=False
    self.lock=threading.Lock()
    self.seedStatus=self.STATE_INACTIVE
    self.info=""
    self.logHandler=logHandler
    self.currentLog=None
    self.cacheNames=None
    self.selectionName=None
    self.pause=False
    self.configDirs=configDirs

  def logDebug(self,fmt,*args):
    if (self.logHandler):
      self.logHandler.debug(fmt,*args)
  def logInfo(self,fmt,*args):
    if (self.logHandler):
      self.logHandler.log(fmt,*args)
  def logError(self,fmt,*args):
    if (self.logHandler):
      self.logHandler.error(fmt,*args)

  def _nowTs(self,useLong=False):
    if useLong:
      return datetime.datetime.now().strftime('%Y%m%d-%H%M%s')
    else:
      return datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
  def _currentConfig(self):
    return os.path.join(self.workdir,self.CURRENT_CONFIG)
  def _progressFile(self):
    return os.path.join(self.workdir,self.PROGRESS_FILE)
  def _infoFile(self):
    return os.path.join(self.workdir,self.INFOFILE)
  def _logFile(self):
    suffix=self._nowTs(True)
    return os.path.join(self.workdir,self.LOGFILE+"."+suffix)
  def _writeInfoFile(self):
    info={
      'selection':self.selectionName,
      'caches': self.cacheNames or []
    }
    try:
      with open(self._infoFile(),"w") as fh:
        yaml.safe_dump(info,fh)
    except Exception as e:
      pass

  def _readFromInfo(self):
    try:
      with open(self._infoFile(), "r") as fh:
        info=yaml.safe_load(fh)
        self.cacheNames=info.get('caches',[])
        self.selectionName=info.get('selection','')
    except Exception as e:
      pass

  def _startSeed(self,newConfig=None):
    self.lock.acquire()
    try:
      if self.pause:
        raise PausedException()
      otherStarting=self.currentlyStarting
      if not otherStarting:
        if self.child is not None:
          raise OtherRunningException()
        self.currentlyStarting=True
    finally:
      self.lock.release()
    if otherStarting:
      raise OtherRunningException()
    try:
      if newConfig is not None:
        with open(self._currentConfig(),"w") as fh:
          yaml.safe_dump(newConfig,fh)
      self.currentLog=self._logFile()
      loghandle=open(self.currentLog,"w")
      self.logInfo("starting new seed")
      env=os.environ.copy()
      env[ENV_PID]=str(os.getpid())
      self.child=subprocess.Popen([sys.executable,
                                 __file__,
                                 '-s', self._currentConfig(),
                                 '-f',self.configFile,
                                 '-p',",".join(self.configDirs),
                                 '-c','1',
                                 '--progress-file', self._progressFile(),
                                   '--continue'],
                                  env=env,
                                  stdout=loghandle,
                                  stderr=subprocess.STDOUT,
                                  stdin=subprocess.DEVNULL,
                                  preexec_fn=os.setsid)
      self._writeInfoFile()
      self.seedStatus=self.STATE_RUNNING
      self.info="started at %s"%self._nowTs()
      return True
    finally:
      self.currentlyStarting=False

  def cleanupLogs(self):
    logs=list(filter(lambda e: e.startswith(self.LOGFILE),os.listdir(self.workdir)))
    logs.sort()
    logs=logs[0:-self.keepLogs]
    for l in logs:
      fn=os.path.join(self.workdir,l)
      try:
        self.logInfo("removing seed log %s",fn)
        os.unlink(fn)
      except:
        pass

  def checkRestart(self):
    '''
    check if we need to restart the seed
    :return:
    '''
    if self.child is not None:
      return False
    self.pause=False
    if not os.path.exists(self._currentConfig()):
      try:
        os.unlink(self._progressFile())
      except:
        pass
      return False
    self._readFromInfo()
    return self._startSeed()
  def runSeed(self,seedConfig,cacheNames=None,selectionName=None):
    if self.checkRunning():
      raise OtherRunningException()
    self.cacheNames=cacheNames
    self.selectionName=selectionName
    self._startSeed(seedConfig)

  def killRun(self,setPaused=False):
    child=self.child
    if child is None:
      if self.pause and not setPaused:
        self._cleanupFiles()
        self.pause=False
        self.info="seed stopped while paused"
      return False
    self.pause=setPaused
    pgrp = os.getpgid(self.child.pid)
    os.killpg(pgrp, signal.SIGINT)
    wt=10
    while wt > 0:
      if not self.checkRunning():
        return True
      time.sleep(0.1)
      wt-=1
    raise Exception("unable to stop")

  def _cleanupFiles(self):
    try:
      os.replace(self._currentConfig(), os.path.join(self.workdir, self.LAST_CONFIG))
    except:
      pass
    try:
      os.unlink(self._currentConfig())
    except:
      pass
    try:
      os.unlink(self._progressFile())
    except:
      pass
    try:
      os.unlink(self._infoFile())
    except:
      pass


  def checkRunning(self):
    '''
    must be called regularly to check if
    a seed is finished
    will reset
    :return:
    '''
    if self.child is None:
      return False
    rt=self.child.poll()
    if rt is None:
      return True
    if self.pause:
      self.logInfo("seed paused")
    else:
      self.logInfo("seed finished with status %d",rt)
    self.lock.acquire()
    try:
      if not self.pause:
        self._cleanupFiles()
      self.child=None
      if self.pause:
        self.seedStatus=self.STATE_INACTIVE
        self.info="seed paused"
      else:
        if rt == 0:
          self.seedStatus=self.STATE_OK
          self.info="seed finished at %s"%self._nowTs()
        else:
          self.seedStatus=self.STATE_ERROR
          self.info="seed returned with state %d at %s"%(rt,self._nowTs())
    finally:
      self.lock.release()
    self.cleanupLogs()
    return False

  def getStatus(self):
    return {
      'status':self.seedStatus,
      'info':self.info,
      'name':self.cacheNames,
      'selection': self.selectionName,
      'paused':self.pause,
      'logFile':os.path.basename(self.currentLog) if self.currentLog is not None else None
    }

  def getLogFile(self,name,bytesFromEnd=None):
    '''
    get an open handle for the logfile (binary mode)
    :param name:
    :return:
    '''
    if name is None:
      return
    for f in os.listdir(self.workdir):
      if not f.startswith(self.LOGFILE):
        continue
      if f == name:
        fname=os.path.join(self.workdir,f)
        st=os.stat(fname)
        size=st.st_size
        fh=open(fname,'rb')
        if bytesFromEnd is not None:
          if bytesFromEnd> size:
            bytesFromEnd=size
          spos=size-bytesFromEnd
          fh.seek(spos)
        return fh



class SeedMain(object):
  def __init__(self):
    self.status=-1
    self.runner=None
  def start(self):
    from pkg_resources import load_entry_point
    self.status = load_entry_point('MapProxy', 'console_scripts', 'mapproxy-seed')()
    return self.status
  def startThread(self):
    self.runner = threading.Thread(target=self.start)
    self.runner.setDaemon(True)
    self.runner.start()
  def isAlive(self):
    if self.runner is None:
      return False
    return self.runner.isAlive()


if __name__ == '__main__':
  #we run mapproxy seed
  #if we have an ENV_PID in the environment we exit if this pid is not available
  cfgFile=None
  seedFile=None
  lastFlag=None
  cfgDirs=''
  hasP=False
  for arg in sys.argv[1:]:
    if arg == '-f' or arg == '-s' or arg == '-p':
      lastFlag=arg
      continue
    if lastFlag == '-f':
      cfgFile=arg
    if lastFlag == '-s':
      seedFile=arg
    if lastFlag == '-p':
      hasP=True
      cfgDirs=arg
    lastFlag=None

  if not cfgFile:
    print("no parameter -f found",file=sys.stderr)
    sys.exit(1)
  if not seedFile:
    print("no parameter -s found",file=sys.stderr)
    sys.exit(1)
  if hasP:
    sys.argv.remove('-p')
    sys.argv.remove(cfgDirs)
  cfgDirs=cfgDirs.split(',')
  cfgDirs.append(os.path.dirname(cfgFile))  
  injector=injector.Injector(cfgDirs)
  injector.checkCreatedIfNeeded(cfgFile)
  seedMain=SeedMain()
  parentPid=os.environ.get(ENV_PID)
  if parentPid is not None:
    parentPid=int(parentPid)
    print("start checking parent pid %d"%parentPid)
    seedMain.startThread()
    while True:
      try:
        rs = os.kill(parentPid, 0)
      except:
        # pid not there any more
        print("parent pid %d not available any more, stopping" % parentPid)
        pgrp = os.getpgid(os.getpid())
        os.killpg(pgrp, signal.SIGINT)
        sys.exit(1)
      if not seedMain.isAlive():
        print("main thread stopped, exiting")
        sys.exit(seedMain.status)
      time.sleep(0.5)
  else:
    sys.exit(seedMain.start())



