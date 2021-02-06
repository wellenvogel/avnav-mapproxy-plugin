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
  NAME_PREFIX='mp-'
  MPREFIX="mapproxy"
  ICONFILE="logo.png"
  WD_SELECTIONS='selections'
  WD_SEED='seed'
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
      'config': [
        {
          'name': 'dataDir',
          'description': 'the directory to store the mapproxy config (defaults to DATADIR/mapproxy), you can use $DATADIR in the path',
          'default': None
        },
        {
          'name': 'chartQueryPeriod',
          'description': 'how often to query charts(s)',
          'default': 5
        },

        {
          'name': 'maxTiles',
          'description': 'max allowed tiles for one seed',
          'default': 100000
        }

        ],
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
      rt.append(chart)
    self.charts=rt
    return rt

  def _getDataDir(self,subDir=None):
    if subDir is None:
      return self.dataDir
    return os.path.join(self.dataDir,subDir)

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

  def run(self):
    """
    the run method
    this will be called after successfully instantiating an instance
    this method will be called in a separate Thread
    The example simply counts the number of NMEA records that are flowing through avnav
    and writes them to the store every 10 records
    @return:
    """
    try:
      avnavData=self.api.getDataDir()
      self.dataDir=self._getConfigValue('dataDir')
      if self.dataDir is not None:
        self.dataDir=self.dataDir.replace('$DATADIR',avnavData)
      else:
        self.dataDir=os.path.join(avnavData,'mapproxy')
      for d in [None,self.WD_SELECTIONS,self.WD_SEED]:
        dirpath=self._getDataDir(d)
        if not os.path.exists(dirpath):
          os.makedirs(dirpath)
        if not os.path.isdir(dirpath):
          raise Exception("unable to create data directory %s"%dirpath)
      configFiles=[self.BASE_CONFIG,self.USER_CONFIG]
      for f in configFiles:
        outname=os.path.join(self.dataDir,f)
        if not os.path.exists(outname) or f == self.BASE_CONFIG:
          src=os.path.join(os.path.dirname(__file__),f)
          if not os.path.exists(src):
            self.api.setStatus("ERROR","config template %s not found"%src)
            return
          self.api.log('creating config file %s from template %s',outname,src)
          shutil.copyfile(src,outname)
      self.maxTiles=int(self._getConfigValue('maxTiles'))
      self.mapproxy=mapproxyWrapper.MapProxyWrapper(self.api.getBaseUrl()+"/api/"+self.MPREFIX,
                                                os.path.join(self.dataDir,self.USER_CONFIG),
                                                self.api)
      self.seedRunner=seedRunner.SeedRunner(self._getDataDir(self.WD_SEED),
                                            os.path.join(self.dataDir, self.USER_CONFIG),
                                            self.api)
      self.seedRunner.checkRestart()
      # we register an handler for API requestscreateSeed(boundsFile,seedFile,name,cache,logger=None):
      self.api.registerRequestHandler(self.handleApiRequest)
      guiPath="gui/index.html"
      testPath=self._getConfigValue('guiPath')
      if testPath is not None:
        guiPath=testPath
      self.api.registerUserApp(self.api.getBaseUrl() + "/"+guiPath, "logo.png")
      self.api.registerChartProvider(self.listCharts)
      self.queryPeriod=int(self._getConfigValue('chartQueryPeriod'))
    except Exception as e:
      self.api.error("error in startup: %s",traceback.format_exc())
      self.api.setStatus("ERROR","exception in startup: %s"%str(e))
      return
    self.api.log("started")
    configFile = os.path.join(self.dataDir, self.USER_CONFIG)
    self.api.setStatus("INACTIVE","starting with config file %s"%configFile)
    while True:
      try:
        rt=self.mapproxy.createProxy(True)
        if rt:
          self.sequence+=1
        self.api.setStatus('NMEA','mapproxy created with config file %s'%configFile)
      except Exception as e:
        self.api.setStatus('ERROR','unable to create mapproxy with config %s: %s'%
                           (configFile,str(e)))
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
      time.sleep(self.queryPeriod)

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
        rt={'status': 'OK','sequence':self.sequence}
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
      if url == 'saveSelection':
        data=self._getRequestParam(args,'data')
        name=self._getRequestParam(args,'name')
        startSeed=self._getRequestParam(args,'startSeed',raiseMissing=False)
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
          (numTiles, seeds) = seedCreator.createSeed(outname, seedName, caches, logger=self.api)
          if numTiles > self.maxTiles:
            return {'status':'number of tiles %d larger then allowed %s'%(numTiles,self.maxTiles)}
          self.seedRunner.runSeed(seeds, caches,selectionName=self._safeName(name))
          return {'status':'OK','numTiles':numTiles}
        return {'status':'OK'}

      if url == 'killSeed':
        self.seedRunner.killRun()
        return {'status':'OK'}

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
        return {'status':'OK'}

      if url == 'loadSelection':
        name = self._getRequestParam(args,'name')
        fname = self._getSelectionFile(name)
        if not os.path.exists(fname):
          return {'status':'file %s not found'%fname}
        with open(fname,"r") as fh:
          data=yaml.safe_load(fh)
        return {'status':'OK','data':data}
    except Exception as e:
      return {'status':str(e)}
    if url == 'getLog':
      status=self.seedRunner.getStatus()
      fh=self.seedRunner.getLogFile(status.get('logFile'),100000)
      if fh is None:
        raise Exception("no log file")
      handler.send_response(200, "OK")
      handler.send_header('Content-Type', 'text/plain')
      handler.send_header("Last-Modified", handler.date_time_string())
      handler.end_headers()
      handler.close_connection=True
      shutil.copyfileobj(fh,handler.wfile)
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


