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
import importlib.util
import io
import json
import os
import re
import shutil
import sys
import threading
import time
import traceback
import urllib.parse
from datetime import datetime


import yaml

from xml.sax.saxutils import escape


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

seedCreator=loadModuleFromFile('create_seed.py')
seedRunner=loadModuleFromFile('seed_runner.py')
mapproxyWrapper=loadModuleFromFile('mapproxy_wrapper.py')
networkChecker=loadModuleFromFile('network.py')

NAME="mapproxy"


def merge_dict(conf, base):
  """
  Return `base` dict with values from `conf` merged in.
  """
  for k, v in conf.items():
    if k not in base:
      base[k] = v
    else:
      if isinstance(base[k], dict):
        merge_dict(v, base[k])
      else:
        base[k] = v
  return base

class MissingParameterException(Exception):
  def __init__(self,name):
    super().__init__("mssing or invalid parameter %s"%name)

class Plugin:
  BASE_CONFIG='avnav_base.yaml'
  USER_CONFIG='avnav_user.yaml'
  INCLUDE_CONFIG='avnav_include.yaml'
  NAME_PREFIX='mp-'
  MPREFIX="mapproxy"
  ICONFILE="logo.png"
  WD_SELECTIONS='selections'
  WD_SEED='seed'
  WD_LAYERS="layers"
  WD_ALL=[WD_LAYERS,WD_SEED,WD_SELECTIONS]
  NW_AUTO='auto'
  NW_ON='on'
  NW_OFF='off'
  RT_OK={'status':'OK'}
  NETWORK_MODES=[NW_AUTO,NW_OFF,NW_ON]
  CONFIG_TEMPLATE="avnav_template.yaml"
  AVNAV_XML = """<?xml version="1.0" encoding="UTF-8" ?>
    <TileMapService version="1.0.0" >
     <Title>%(title)s</Title>
     <TileMaps>
       <TileMap 
         title="%(title)s" 
         href="%(url)s"
         minzoom="%(minzoom)s"
         maxzoom="%(maxzoom)s"
         projection="EPSG:4326">
               <BoundingBox minlon="%(minlon)f" minlat="%(minlat)f" maxlon="%(maxlon)f" maxlat="%(maxlat)f" title="layer"/>
         <TileFormat width="256" height="256" mime-type="x-%(format)s" extension="%(format)s" />
      </TileMap>       
     </TileMaps>
   </TileMapService>

    """

  CONFIG=[
           {
             'name': 'dataDir',
             'description': 'the directory to store the mapproxy config (defaults to DATADIR/mapproxy), you can use $DATADIR in the path',
             'default': None
           },
           {
             'name': 'chartQueryPeriod',
             'description': 'how often to query charts(s)',
             'default': 5
           }
         ]
  CONFIG_EDIT=[
    {
      'name': 'maxTiles',
      'description': 'max allowed tiles for one seed',
      'type': 'NUMBER',
      'default': 200000
    },
    {
      'name': 'networkMode',
      'description': 'the initial state of the internet connection when AvNav is starting',
      'type': 'SELECT',
      'rangeOrList': NETWORK_MODES,
      'default': 'auto'
    },
    {
      'name': 'checkHost',
      'description': 'hostname to use for network checks',
      'default': 'www.wellenvogel.de'
    }
  ]
  @classmethod
  def pluginInfo(cls):
    """
    the description for the module
    @return: a dict with the content described below
            parts:
               * description (mandatory)
               * data: list of keys to be stored (optional)
                 * path - the key - see AVNApi.addData, all pathes starting with "gps." will be sent to the GUI
                 * description
    """
    return {
      'description': 'mapproxy plugin',
      'config': cls.CONFIG+cls.CONFIG_EDIT,
      'data': [
      ]
    }

  def __init__(self,api):
    """
        initialize a plugins
        do any checks here and throw an exception on error
        do not yet start any threads!
        @param api: the api to communicate with avnav
        @type  api: AVNApi
    """
    self.api = api # type: AVNApi
    self.dataDir=None
    self.mapproxy=None
    self.sequence=time.time()
    self.charts=[]
    self.layer2caches={}
    self.queryPeriod=5
    self.seedRunner=None
    self.maxTiles=100000
    self.boxes=None
    self.networkMode=self.NW_AUTO
    self.networkAvailable=None
    self.networkHost=None
    self.networkChecker=None
    self.condition=threading.Condition()
    if hasattr(self.api,'registerEditableParameters'):
      self.api.registerEditableParameters(self.CONFIG_EDIT,self._changeConfig)
    if hasattr(self.api,'registerRestart'):
      self.api.registerRestart(self._apiRestart)
    self.changeSequence=0
    self.startSequence=0


  def _apiRestart(self):
    self.startSequence+=1

  def _changeConfig(self,newValues):
    networkMode=newValues.get('networkMode')
    if networkMode is not None:
      if networkMode not in self.NETWORK_MODES:
        raise Exception("invalid network mode")
      self.networkMode=networkMode
    networkHost=newValues.get('checkHost')
    if networkHost is not None:
      self.networkHost=networkHost
      self.networkChecker.host=networkHost
    maxTiles=newValues.get('maxTiles')
    if maxTiles is not None:
      self.maxTiles=int(maxTiles)
    self.api.saveConfigValues(newValues)
    self.changeSequence+=1
  def _getConfigValue(self, name):
    defaults=self.pluginInfo()['config']
    for cf in defaults:
      if cf['name'] == name:
        return self.api.getConfigValue(name, cf.get('default'))
    return self.api.getConfigValue(name)


  def _getLayers(self):
    rt={}
    for chart in self.charts:
      name=chart.get('internal',{}).get('layer')
      if name is None:
        continue
      rt[name]=chart.copy()
      rt[name]['caches']=self.layer2caches.get(name,[])
    return rt


  def _getMaps(self):
    rt=[]
    if self.mapproxy is None:
      self.api.debug("mapproxy not initialized in getMaps")
      return rt
    mplist=self.mapproxy.getMaps()
    internalPath = self.MPREFIX + "/tiles/1.0.0"
    chartBase = self.api.getBaseUrl() + "/api/" + internalPath
    iconUrl = self.api.getBaseUrl() + "/" + self.ICONFILE
    for chart in mplist:
      if chart.get('internal') is None:
        continue
      internals=chart['internal']
      internals['path']=internalPath+"/"+internals.get('path','')
      chart['name']=self.NAME_PREFIX+chart.get('name','')
      chart['url']=chartBase+"/"+chart.get('url','')
      chart['icon']= iconUrl
      chart['sequence']=self.sequence
      chart['upzoom']=True
      rt.append(chart)
    self.charts=rt
    return rt

  def _getDataDir(self,subDir=None,create=False):
    if subDir is None:
      rt=self.dataDir
    else:
      rt=os.path.join(self.dataDir,subDir)
    if not os.path.exists(rt) and create:
      os.makedirs(rt)
    return rt


  def _listSelections(self):
    rt=[]
    for f in os.listdir(self._getDataDir(self.WD_SELECTIONS)):
      if f.endswith('.yaml'):
        rt.append(f.replace('.yaml',''))
    return rt

  def _safeName(self, name):
    return re.sub('[^a-zA-Z0-9_.,-]','',name)

  def listCharts(self, hostip):
    self.api.debug("listCharts %s" % hostip)
    rt=[]
    try:
      for c in self.charts:
        entry=c.copy()
        del entry['internal']
        rt.append(entry)
    except:
      self.api.debug("unable to list charts: %s" % traceback.format_exc())
      return []
    return rt

  def _getCacheFile(self,cacheName,checkExistance=False):
    for clist in self.layer2caches.values():
      for c in clist:
        if c.get('name') == cacheName:
          cfg=c.get('cache')
          if cfg is None:
            continue
          if cfg.get('type') == 'mbtiles' and cfg.get('filename') is not None:
            name=cfg.get('filename')
            if not os.path.isabs(name):
              name=os.path.join(self.dataDir,'cache_data',name)
            if not checkExistance:
              return name
            if os.path.exists(name):
              return name

  def _wakeupLoop(self):
    self.condition.acquire()
    try:
      self.condition.notifyAll()
    finally:
      self.condition.release()

  def _waitLoop(self,time):
    self.condition.acquire()
    try:
      self.condition.wait(time)
    finally:
      self.condition.release()

  def _getSystemConfigDir(self):
    return os.path.join(os.path.dirname(__file__),'sources')
  def _listConfigs(self,includeUser=False):
    rt=[]
    alreadySeen=[]
    if includeUser:
      userPath=os.path.join(self._getDataDir(),self.USER_CONFIG)
      if os.path.exists(userPath):
        rt.append({'path':userPath,'name':self.USER_CONFIG,'editable':True})
        alreadySeen.append(self.USER_CONFIG)
    userDir=self._getDataDir(self.WD_LAYERS)
    for cfgDir in [userDir,self._getSystemConfigDir()]:
      for f in os.listdir(cfgDir):
        if not f.endswith('.yaml'):
          continue
        if f == self.BASE_CONFIG:
            continue
        if f in alreadySeen:
          continue
        rt.append({'path':os.path.join(cfgDir,f),'name':f,'editable':cfgDir == userDir})
    return rt

  def _getMainConfig(self):
    return os.path.join(self._getDataDir(),self.INCLUDE_CONFIG)

  def _addRemoveInclude(self,data,include,add=True):
    includes=data.get('base')
    if includes is None:
      includes=[]
      data['base']=includes
    if add:
      if not include in includes:
        includes.append(include)
        return True
      return False
    if include in includes:
      includes.remove(include)
      return True
    return False

  def run(self):
    """
    the run method
    this will be called after successfully instantiating an instance
    this method will be called in a separate Thread
    The example simply counts the number of NMEA records that are flowing through avnav
    and writes them to the store every 10 records
    @return:
    """
    startSequence=self.startSequence
    try:
      avnavData=self.api.getDataDir()
      self.dataDir=self._getConfigValue('dataDir')
      if self.dataDir is not None:
        self.dataDir=self.dataDir.replace('$DATADIR',avnavData)
      else:
        self.dataDir=os.path.join(avnavData,'mapproxy')
      for d in self.WD_ALL:
        dirpath=self._getDataDir(d,True)
        if not os.path.isdir(dirpath):
          raise Exception("unable to create data directory %s"%dirpath)
      mainCfg=self._getMainConfig()
      legacyBase=os.path.join(self._getDataDir(),self.BASE_CONFIG)
      if os.path.exists(legacyBase):
        self.api.log("renaming old %s to %s.old"%(legacyBase,legacyBase))
        os.rename(legacyBase,legacyBase+".old")
      if not os.path.exists(mainCfg):
        self.api.log("creating main cfg %s"%mainCfg)
        data={}
        self._addRemoveInclude(data, self.BASE_CONFIG, True)
        userConfig = os.path.join(self.dataDir, self.USER_CONFIG)
        if os.path.exists(userConfig):
          self._addRemoveInclude(data, self.USER_CONFIG, True)
        for i in self._listConfigs():
          self._addRemoveInclude(data,i['name'],True)
        yamldata = yaml.dump(data)
        self._safeWriteFile(mainCfg,yamldata)
      else:
        with open(mainCfg,'r') as mh:
          mainData=yaml.safe_load(mh)
          hasChanged=False
          if self._addRemoveInclude(mainData,self.BASE_CONFIG,True):
            hasChanged=True
            self.api.log("repairing missing %s in %s"%(self.BASE_CONFIG,mainCfg))
          includes=(mainData.get('base') or []) + []
          for include in includes:
            try:
                self._getLayerConfig(include,True,True)
            except:
                self._addRemoveInclude(mainData,include,False)
                self.api.log("repairing %s, remove non existent %s"%(mainCfg,include))
                hasChanged=True
          if hasChanged:
            self._safeWriteFile(mainCfg,yaml.dump(mainData))
      self.maxTiles=int(self._getConfigValue('maxTiles'))
      configDirs=[self._getDataDir(),self._getDataDir(self.WD_LAYERS),self._getSystemConfigDir()]
      self.mapproxy=mapproxyWrapper.MapProxyWrapper(self.api.getBaseUrl()+"/api/"+self.MPREFIX,
                                                os.path.join(self.dataDir,self.INCLUDE_CONFIG),
                                                configDirs,
                                                self.api)
      self.seedRunner=seedRunner.SeedRunner(self._getDataDir(self.WD_SEED),
                                            self.mapproxy.getConfigName(False), #only if online...
                                            self.api)
      self.seedRunner.checkRestart()
      # we register an handler for API requestscreateSeed(boundsFile,seedFile,name,cache,logger=None):
      self.api.registerRequestHandler(self.handleApiRequest)
      self.boxes=seedCreator.Boxes(logHandler=self.api,additionalBoxes=True)
      guiPath="gui/index.html"
      testPath=self._getConfigValue('guiPath')
      if testPath is not None:
        guiPath=testPath
      self.api.registerUserApp(self.api.getBaseUrl() + "/"+guiPath, "logo.png")
      self.api.registerChartProvider(self.listCharts)
      self.queryPeriod=int(self._getConfigValue('chartQueryPeriod'))
      self.networkMode=self._getConfigValue('networkMode')
      if not self.networkMode in self.NETWORK_MODES:
        raise Exception("invalid newtork mode %s, allowed: %s"%
                        (self.networkMode,",".join(self.NETWORK_MODES)))
      self.networkHost=self._getConfigValue('checkHost')
      self.networkChecker=networkChecker.NetworkChecker(self.networkHost,checkInterval=max(60,self.queryPeriod*5))
      self.networkChecker.available(True)
      if self.networkMode == self.NW_OFF:
        self.networkAvailable=False
      else:
        #assume True for auto until first check...
        self.networkAvailable=True
    except Exception as e:
      self.api.error("error in startup: %s",traceback.format_exc())
      self.api.setStatus("ERROR","exception in startup: %s"%str(e))
      raise
    self.api.log("started")
    configFile = os.path.join(self.dataDir, self.INCLUDE_CONFIG)
    self.api.setStatus("INACTIVE","starting with config file %s"%configFile)
    while startSequence == self.startSequence:
      incrementSequence=False
      restartProxy=False
      try:
        if self.networkMode == self.NW_AUTO:
          available=self.networkChecker.available(True)
        else:
          available=True if self.networkMode==self.NW_ON else False
        if available != self.networkAvailable and available is not None:
          self.api.log("network state changed to %s",str(available))
          restartProxy=True
          self.networkAvailable=available
          #TODO: pause seed
      except Exception as e:
        self.api.debug("error in network check: %s",str(e))
      try:
        rt=self.mapproxy.createProxy(changedOnly=not restartProxy,isOffline=not self.networkAvailable)
        if rt:
          incrementSequence=True
        self.api.setStatus('NMEA','mapproxy created with config file %s'%configFile)
      except Exception as e:
        self.api.setStatus('ERROR','unable to create mapproxy with config %s: %s'%
                           (configFile,str(e)))
      if restartProxy:
        if self.networkAvailable:
          self.seedRunner.checkRestart() #could have been paused
        else:
          self.seedRunner.killRun(setPaused=True)
      try:
        if self.seedRunner is not None:
          self.seedRunner.checkRunning()
      except Exception as e:
        self.api.debug("Exception when checking seed runner: %s",str(e))
      try:
        self._getMaps()
      except Exception as e:
        self.api.debug("error in main loop: %s",traceback.format_exc())
      try:
        self.layer2caches=self.mapproxy.getMappings()
      except Exception as e:
        self.api.debug("error in main loop reading config: %s",traceback.format_exc())
      if incrementSequence:
        self.sequence += 1
      self._waitLoop(self.queryPeriod)


  def _findChartEntry(self,path):
    for ce in self.charts:
      internals=ce.get('internal')
      if internals is None:
        continue
      if internals.get('path') == path:
        return ce

  def _getSelectionFile(self,name):
    name=self._safeName(name)
    return os.path.join(self._getDataDir(self.WD_SELECTIONS),name+".yaml")
  def _getRequestParam(self,param,name,raiseMissing=True):
    data = param.get(name)
    if data is None or len(data) != 1:
      if not raiseMissing:
        return None
      raise MissingParameterException(name)
    return data[0]
  
  def _getLayerConfig(self,name,raiseMissing=False,useAllDirs=False):
    safeName=self._safeName(name) 
    if name != safeName:
      raise Exception("invalid name")
    dirs=[]
    if not name.endswith('.yaml'):
      name+=".yaml"
    if not useAllDirs:
        dirs=[self._getDataDir(self.WD_LAYERS)]
        if name == self.USER_CONFIG:
            dirs=[self._getDataDir()]
    else:
        dirs=[self._getDataDir(self.WD_LAYERS),self._getDataDir(),self._getSystemConfigDir()]
    #try to find an existing one
    for dir in dirs:
        fn=os.path.join(dir,name)
        if os.path.exists(fn):
            return fn
    if not raiseMissing:  
      return os.path.join(dirs[0],name)
    raise Exception("layer config %s not found"%safeName)

  def _safeWriteFile(self,fileName,data):
    tmpname=fileName+".tmp%s"%str(time.time())
    with open(tmpname,"w") as oh:
      oh.write(data)
      oh.close()
      try:
        os.replace(tmpname,fileName)
      except Exception as e:
        try:
          os.unlink(tmpname)
        except:
          pass
        raise

  def _checkAndEnableLayer(self,name,layerData,enable=None):
    try:
      parsed = yaml.safe_load(layerData)
    except Exception as e:
      return {'status': 'invalid yaml: %s' % str(e)}
    if not name.endswith('.yaml'):
      name += '.yaml'
    cfg={}
    with open(self._getMainConfig(), 'r') as mh:
      cfg = yaml.safe_load(mh)
    enabledChanged=False
    if enable is not None:
        enabledChanged = self._addRemoveInclude(cfg, name, enable)
    self.mapproxy.parseAndCheckConfig(
      offline=not self.networkAvailable,
      cfg=cfg.copy(),
      baseData={name: parsed}
    )
    if enabledChanged:
      self.api.log("change layer %s enabled=%s"%(name,enable))
      self._safeWriteFile(self._getMainConfig(), yaml.dump(cfg))

  def handleApiRequest(self,url,handler,args):
    """
    handler for API requests send from the JS
    @param url: the url after the plugin base
    @param handler: the HTTP request handler
                    https://docs.python.org/2/library/basehttpserver.html#BaseHTTPServer.BaseHTTPRequestHandler
    @param args: dictionary of query arguments
    @return:
    """
    try:
      if url == 'status':
        rt={'status': 'OK',
            'sequence':self.sequence,
            'networkMode': self.networkMode,
            'networkAvailable':self.networkAvailable
            }
        if self.seedRunner is not None:
          rt['seed']=self.seedRunner.getStatus()
        if self.mapproxy is not None:
          rt['mapproxy']=self.mapproxy.getStatus()
        return rt
      if url == 'layers':
        return {
          'status':'OK',
          'data': self._getLayers()
        }
      if url == 'setNetworkMode':
        mode=self._getRequestParam(args,'mode')
        if mode not in self.NETWORK_MODES:
          raise Exception("invalid mode %s, allowed: %s"%(mode,",".join(self.NETWORK_MODES)))
        self.networkMode=mode
        self._wakeupLoop()
        return self.RT_OK
      if url == 'saveSelection':
        data=self._getRequestParam(args,'data')
        name=self._getRequestParam(args,'name')
        startSeed=self._getRequestParam(args,'startSeed',raiseMissing=False)
        if startSeed is not None and not self.networkAvailable:
          return {'status':'cannot start seed without network'}
        outname=self._getSelectionFile(name)
        decoded=json.loads(data)
        with open(outname,"w") as oh:
          yaml.dump(decoded,oh)
        if startSeed is not None:
          layerName=startSeed
          caches=self.layer2caches.get(layerName)
          if caches is None:
            return {'status':'no caches found for layer %s'%layerName}
          seedName = "seed-" + datetime.now().strftime('%Y%m%d-%H%M%s')
          cacheNames=list(map(lambda x:x['name'],caches))
          reloadDays=self._getRequestParam(args,'reloadDays',raiseMissing=False)
          (numTiles, seeds) = seedCreator.createSeed(outname, seedName,
                                                     cacheNames,
                                                     logger=self.api,
                                                     reloadDays=reloadDays)
          if numTiles > self.maxTiles:
            return {'status':'number of tiles %d larger then allowed %s'%(numTiles,self.maxTiles)}
          self.seedRunner.runSeed(seeds, cacheNames,selectionName=self._safeName(name))
          return {'status':'OK','numTiles':numTiles}
        return self.RT_OK

      if url == 'killSeed':
        self.seedRunner.killRun()
        return self.RT_OK

      if url == 'countTiles':
        data=self._getRequestParam(args,'data')
        rt=seedCreator.countTiles(json.loads(data),self.api)
        return {'status':'OK','numTiles':rt,'allowed':self._getConfigValue('maxTiles')}
      if url == 'listSelections':
        return {'status':'OK','data':self._listSelections()}

      if url == 'deleteSelection':
        name = self._getRequestParam(args,'name')
        fname=self._getSelectionFile(name)
        if os.path.exists(fname):
          os.unlink(fname)
        return self.RT_OK

      if url == 'loadSelection':
        name = self._getRequestParam(args,'name')
        fname = self._getSelectionFile(name)
        if not os.path.exists(fname):
          return {'status':'file %s not found'%fname}
        with open(fname,"r") as fh:
          data=yaml.safe_load(fh)
        return {'status':'OK','data':data}

      if url == 'createLayer':
        name= self._getRequestParam(args,'name',raiseMissing=True)
        configFile=self._getLayerConfig(name)
        if os.path.exists(configFile):
          raise Exception("config already exists")
        template=os.path.join(os.path.dirname(__file__),self.CONFIG_TEMPLATE)
        with open(template,'r') as th:
          templateData=th.read()
          templateData=templateData.replace('##LAYER##',name)
          with open(configFile,'w') as ch:
            ch.write(templateData)
        if not os.path.exists(configFile):
          raise Exception("unable to create %s from template"%configFile)
        with open(configFile,"r") as fh:
          data=fh.read()
        return {'status':'OK','data':data}
      if url == 'editLayer':
        name= self._getRequestParam(args,'name',raiseMissing=True)
        configFile=self._getLayerConfig(name,True)
        with open(configFile,"r") as fh:
          data=fh.read()
        return {'status':'OK','data':data}
      if url == 'saveLayer':
        name= self._getRequestParam(args,'name')
        data = self._getRequestParam(args, 'data')
        configFile=self._getLayerConfig(name,raiseMissing=True)
        self._checkAndEnableLayer(name,data)
        self._safeWriteFile(configFile,data)
        self._wakeupLoop()  
        return self.RT_OK
      if url == 'listConfigs':
        with open(self._getMainConfig(),'r') as mh:
            mainCfg=yaml.safe_load(mh)
        includes=mainCfg.get('base') or []
        data=self._listConfigs(True)
        for entry in data:
          entry['enabled']=entry['name'] in includes
        return {'status':'OK','data':data}
      if url == 'enableLayer':
        name = self._getRequestParam(args, 'name',raiseMissing=True)
        config=self._getLayerConfig(name,raiseMissing=True,useAllDirs=True)
        with open(config,'r') as ch:
          layerData=ch.read()
        self._checkAndEnableLayer(name,layerData,True)
        self._wakeupLoop()
        return self.RT_OK
      if url == 'disableLayer':
        name = self._getRequestParam(args, 'name',raiseMissing=True)
        if not name.endswith('.yaml'):
          name+=".yaml"
        with open(self._getMainConfig(),'r') as mh:
          base=yaml.safe_load(mh)
        if self._addRemoveInclude(base,name,False):
          self._safeWriteFile(self._getMainConfig(),yaml.dump(base))
          self._wakeupLoop()
          return self.RT_OK
        return {'status':"config %s not found"%name}
      if url == 'deleteLayer':
        name = self._getRequestParam(args, 'name', raiseMissing=True)
        if not name.endswith('.yaml'):
          name += ".yaml"
        allLayers=self._listConfigs(True)
        for layer in allLayers:
          if layer['name'] == name:
            if not layer['editable']:
              return {'status':"config %s cannot be deleted"%name}
            with open(self._getMainConfig(),'r') as mh:
              base=yaml.safe_load(mh)
            if self._addRemoveInclude(base,name,False):
              self._safeWriteFile(self._getMainConfig(),yaml.dump(base))
            os.unlink(layer['path'])
            self._wakeupLoop()
            return self.RT_OK
        return {'status':'config %s not found'%name}

    except Exception as e:
      return {'status':str(e)}
    
    if url == 'getLog':
      asAttach=self._getRequestParam(args,'attach',raiseMissing=False)
      status=self.seedRunner.getStatus()
      seekBytes=100000
      if asAttach is not None:
        seekBytes=None
      fh=self.seedRunner.getLogFile(status.get('logFile'),seekBytes)
      if fh is None:
        raise Exception("no log file")
      handler.send_response(200, "OK")
      handler.send_header('Content-Type', 'text/plain')
      handler.send_header("Last-Modified", handler.date_time_string())
      if asAttach is not None:
        handler.send_header('Content-Disposition',
                            'attachment;filename="%s"' %os.path.basename(status.get('logFile')) )
      handler.end_headers()
      handler.close_connection=True
      shutil.copyfileobj(fh,handler.wfile)
      return True

    if url == 'getCacheFile':
      name=self._getRequestParam(args,'name')
      fileName=self._getCacheFile(name,checkExistance=True)
      if fileName is None:
        raise Exception("cache file for %s not found"%name)
      with open(fileName,'rb') as fh:
        handler.send_response(200, "OK")
        handler.send_header('Content-Type', 'application/octet-stream')
        handler.send_header("Last-Modified", handler.date_time_string())
        handler.send_header('Content-Disposition',
                           'attachment;filename="%s.mbtiles"'%name)
        st=os.stat(fileName)
        handler.send_header('Content-Length',str(st.st_size))
        handler.end_headers()
        shutil.copyfileobj(fh,handler.wfile)
      return True

    if url == 'getBoxes':
      try:
        nelat = float(self._getRequestParam(args, 'nelat'))
        nelng = float(self._getRequestParam(args, 'nelng'))
        swlat = float(self._getRequestParam(args, 'swlat'))
        swlng = float(self._getRequestParam(args, 'swlng'))
        minZoom = self._getRequestParam(args, 'minZoom',False)
        maxZoom = self._getRequestParam(args, 'maxZoom',False)
        boxlines = self.boxes.getBoxes(nelat, nelng, swlat, swlng, minZoom, maxZoom)
        handler.send_response(200, "OK")
        handler.send_header('Content-Type', 'text/plain')
        handler.send_header("Last-Modified", handler.date_time_string())
        handler.end_headers()
        handler.close_connection = True
        for l in boxlines:
          handler.wfile.write(l)
        return True
      except Exception as e:
        handler.send_response(400, str(e))
        handler.send_header('Content-Type', 'text/plain')
        handler.end_headers()
        handler.wfile.write(traceback.format_exc().encode('utf-8'))
        handler.close_connection=True
        return True
    #mapproxy requests
    if url.startswith(self.MPREFIX):
      if url.endswith('/avnav.xml'):
        path=url.replace('/avnav.xml','')
        chart=self._findChartEntry(path)
        #chartUrl=self.api.getBaseUrl()+"/api/"+url
        chartUrl=''
        parts=url.split("/")
        param={
          'title': escape(parts[-3]),
          'url':chartUrl,
          'minzoom': 6,
          'maxzoom':18,
          'format':'png',
          'minlon':-180,
          'maxlon':180,
          'minlat':-85,
          'maxlat':85
        }
        if chart:
          param.update(chart['internal'])
        response=self.AVNAV_XML%param
        response=response.encode('utf-8')
        handler.send_response(200,"OK")
        handler.send_header('Content-Type','text/xml')
        handler.send_header('Content-Length',str(len(response)))
        handler.send_header("Last-Modified", handler.date_time_string())
        handler.end_headers()
        handler.wfile.write(response)
        return True
      if url.endswith('sequence'):
        return {'status':'OK','sequence':self.sequence}
      self.mapproxy.handleRequest(url,handler,args)
      return
    return {'status','unknown request'}


