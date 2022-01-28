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
import logging
import os
import sys
import traceback
import urllib.parse
from wsgiref.headers import Headers
from wsgiref.simple_server import ServerHandler
import yaml
from mapproxy.wsgiapp import make_wsgi_app
from mapproxy.config.spec import validate_options
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

injector=loadModuleFromFile('injector.py')

class OwnWsgiHeaders(Headers):

  def __init__(self, headers=None):
    if headers is not None:
      nh=[]
      for k,v in headers:
        nh.append((str(k),str(v)))
      headers=nh
    super().__init__(headers)


class OwnWsgiHandler(ServerHandler):
  headers_class = OwnWsgiHeaders

  def _convert_string_type(self, value, title):
    """Convert/check value type."""
    if type(value) is str:
      return value
    return str(value)

class OwnLogHandler(logging.Handler):
  PRFX="MapProxy"
  DEBUG_ONLY=['mapproxy.source.request','mapproxy.config']
  def __init__(self, logger,level=logging.NOTSET):
    self.logger=logger
    super().__init__(level)
    self.fatalError=None

  def emit(self, record):
    if isinstance(record.msg,BaseException):
      exc=record.msg
      estr=traceback.format_exception(etype=type(exc), value=exc, tb=exc.__traceback__)
      for st in estr:
        self.logger.error("%s: %s",self.PRFX,st)
      if record.levelno == logging.FATAL:
        self.fatalError=''.join(estr)
    else:
      logfunction=self.logger.debug
      level=record.levelno
      if level == logging.FATAL:
        self.fatalError=str(record.msg%record.args or None)
      if record.name in self.DEBUG_ONLY and level == logging.INFO:
        level=logging.DEBUG
      if level >= logging.ERROR:
        logfunction=self.logger.error
      elif level >= logging.INFO:
        logfunction=self.logger.log
      if len(record.args) > 0:
        logfunction("%s: %s",self.PRFX,str(record.msg%record.args or None))
      else:
        logfunction("%s: %s", self.PRFX, str(record.msg))

  def getFatalError(self,reset=True):
    rt=self.fatalError
    if reset:
      self.fatalError=None
    return rt

def layerListToDict(l):
  if isinstance(l,dict):
    return l
  rt={}
  for i in l:
    if i.get('name') is None:
      raise Exception("missing name in list layerlist")
    rt[i['name']]=i
  return rt

def layerDictToList(d):
  rt=[]
  for k,v in d.items():
    v['name']=k
    rt.append(v)
  return rt
class MapProxyWrapper(object):
  LOGGERS=['mapproxy']
  def __init__(self,prefix,configFile,configDirs,logger,loglevel=logging.NOTSET):
    self.prefix=prefix
    self.configFile=configFile
    self.normalConfig=configFile+".normal"
    self.offlineConfig=configFile+".offline"
    self.handler=OwnLogHandler(logger)
    for mplog in self.LOGGERS:
      mplogger = logging.getLogger(mplog)
      mplogger.setLevel(logging.INFO) #TODO: debug
      mplogger.addHandler(self.handler)
    self.mapproxy = None
    self.logger=logger
    self.fatalError=None
    self.configTimeStamp = None
    self.layerMappings={}
    self.injector=injector.Injector(configDirs)
    self.configDirs=configDirs

  def _mergeCfg(self,current,base,isFirstLevel=False):
    if not isinstance(base,dict):
      raise Exception("invalid base type - must be dict")
    for k,v in current.items():
      if not k in base:
        base[k]=v
      else:
        if type(base[k]) != type(v):
          #we only allow different types for the
          #old and new style layers on first level
          if k != 'layers' or not isFirstLevel:
            raise Exception("cannot merge different types for key %s: %s <=> %s"%(
              k,str(v),str(base[k])))
          layers=layerListToDict(base[k])
          layers.update(layerListToDict(v))
          base[k]=layerDictToList(layers)
        else:
          if k == 'layers' and isFirstLevel:
            layers = layerListToDict(base[k])
            layers.update(layerListToDict(v))
            base[k] = layerDictToList(layers)
          else:
            if isinstance(base[k],dict):
              self._mergeCfg(v,base[k])
            else:
              base[k]=v
    return base

  def _mergeBaseFiles(self,cfg,baseData=None):
    if 'base' in cfg:
      baseFiles = cfg.pop('base')
      if isinstance(baseFiles, str):
        baseFiles = [baseFiles]
      for base in baseFiles:
        fn=None
        if baseData is not None and baseData.get(base) is not None:
          baseCfg=baseData[base]
        else:  
          if not os.path.isabs(base):
            found=None
            for dir in self.configDirs:
              fn = os.path.join(dir, base)
              if os.path.exists(fn):
                found=fn
                break
            if found is None:
                raise Exception("file %s not found in %s"%(base,",".join(self.configDirs)))
            base=found
          baseCfg = self._loadConfigFile(base,baseData)
        try:
          cfg = self._mergeCfg(cfg.copy(), baseCfg, True)
        except Exception as e:
          if fn is not None:
            raise Exception("error merging %s:%s"%(fn,str(e)))
          else:
            raise
    return cfg

  def _loadConfigFile(self,file,baseData=None):
    if not os.path.exists(file):
      raise Exception("config file %s not found"%file)
    with open(file,"r") as fh:
      cfg=yaml.safe_load(fh)
      fh.close()
    if cfg is None:
        cfg={}
    return self._mergeBaseFiles(cfg,baseData)

  def parseAndCheckConfig(self,offline=False,cfg=None,baseData=None):
    '''
    baseData is a dict baseName->content
    '''
    if cfg is None:
      inputFile=self.configFile
      cfg=self._loadConfigFile(inputFile,baseData)
    else:
      cfg=self._mergeBaseFiles(cfg,baseData=baseData)

    if offline is True:
      sources=cfg.get('sources')
      if sources is not None:
        for k,v in sources.items():
          v['seed_only']=True
    (errors,infoOnly)=validate_options(cfg)
    if not infoOnly:
        raise Exception(",".join(list(filter(lambda a: not a.startswith('unknown'),errors))))
    layer2caches = {}
    layers = cfg.get('layers')
    caches = cfg.get('caches')
    if layers is not None and caches is not None:
      layerlist = []
      if isinstance(layers, list):
        layerlist = layers
      else:
        for k, v in layers.items():
          v['name'] = k
        layerlist = list(layers.values())
      for layer in layerlist:
        name = layer.get('name')
        sources = layer.get('sources', [])
        if name is None:
          continue
        for s in sources:
          if s in caches:
            centry=caches[s].copy()
            centry['name']=s
            cachecfg=centry.get('cache',{})
            centry['hasBefore']=cachecfg.get('type') in ['sqlite','files']
            if layer2caches.get(name) is None:
              layer2caches[name] = []
            layer2caches[name].append(centry)
    return (cfg,layer2caches)

  def getConfigName(self,isOffline):
    return self.normalConfig if not isOffline else self.offlineConfig

  def createConfigAndMappings(self,isOffline=False):
    (cfg,mappings)=self.parseAndCheckConfig(offline=isOffline)
    outname=self.getConfigName(isOffline)
    tmpname=outname+".tmp"
    with open(tmpname,"w") as fh:
      yaml.safe_dump(cfg,fh)
      fh.close()
    try:
      os.replace(tmpname,outname)
    finally:
      try:
        os.unlink(tmpname)
      except:
        pass
    other=self.getConfigName(not isOffline)
    try:
      os.unlink(other)
    except:
      pass
    self.layerMappings=mappings


  def createProxy(self,changedOnly=False,isOffline=False):
    if self.mapproxy is None or self.configTimeStamp is None:
      changedOnly=False
    if not os.path.exists(self.configFile):
      self.mapproxy = None
      raise Exception("config file %s not found",self.configFile)
    st = os.stat(self.configFile)
    if changedOnly:
      if st.st_mtime == self.configTimeStamp:
        self.logger.debug("config file %s not changed",self.configFile)
        return False
    self.fatalError = None
    self.mapproxy = None
    self.configTimeStamp=st.st_mtime
    self.logger.log("creating mapproxy wsgi app with config %s", self.getConfigName(isOffline))
    try:
      self.createConfigAndMappings(isOffline)
      self.injector.checkCreatedIfNeeded(self.getConfigName(isOffline))
      self.mapproxy = make_wsgi_app(self.getConfigName(isOffline), ignore_config_warnings=True, reloader=False)
      self.getFatalError(True)
    except Exception as e:
      self.layerMappings={}
      self.logger.error("unable to create mapProxy: %s",traceback.format_exc())
      self.fatalError=str(e)
      raise

    self.logger.log("created mapproxy wsgi app")
    return True

  def getFatalError(self,reset=True):
    ownError=self.fatalError
    if reset:
      self.fatalError=None
    if ownError is not None:
      return ownError
    return self.handler.getFatalError(reset)

  def getStatus(self):
    status='unknown'
    error=self.getFatalError(False)
    if self.mapproxy is not None:
      status='ok'
      error=None
    elif error is not None:
      status='error'
    return {
      'running': self.mapproxy is not None,
      'status': status,
      'lastError': error
    }
  def getMaps(self):
    rt=[]
    if self.mapproxy is None :
      self.logger.debug("mapproxy not initialized in getMaps")
      return rt
    handlers=self.mapproxy.handlers
    if handlers is None or handlers.get('tiles') is None:
      self.logger.debug("no tiles service in mapproxy in getMaps")
      return rt
    tiles=handlers['tiles']
    for k,v in tiles.layers.items():
      internals={
        'path':k[0]+"/"+k[1],
        'layer':k[0],
        'grid': k[1]
      }
      try:
        #there should be some checks...
        extent=v.extent
        if extent is not None and extent.llbbox is not None:
          internals['minlon']=extent.llbbox[0]
          internals['minlat']=extent.llbbox[1]
          internals['maxlon']=extent.llbbox[2]
          internals['maxlat']=extent.llbbox[3]
        if v.grid is not None and v.grid.tile_sets is not None:
          zooms=[]
          for ts in v.grid.tile_sets:
            zooms.append(ts[0])
          internals['minzoom']=min(zooms)
          internals['maxzoom']=max(zooms)
      except Exception as e:
        self.logger.debug("unable to fetch internals for layer: %s",str(e))
      entry={
        'name': k[0],
        'url': k[0]+"/"+k[1],
        'internal':internals
      }
      rt.append(entry)
    return rt

  def getMappings(self):
    return self.layerMappings


  def _getWsgiEnv(self, handler):
      server_version = "WSGIServer/0.2"

      env = {}
      env['SERVER_NAME'] = 'avnav'
      env['GATEWAY_INTERFACE'] = 'CGI/1.1'
      env['SERVER_PORT'] = str(handler.server.server_port)
      env['REMOTE_HOST'] = ''
      env['CONTENT_LENGTH'] = ''
      env['SCRIPT_NAME'] = ''
      env['SERVER_PROTOCOL'] = handler.request_version
      env['SERVER_SOFTWARE'] = server_version
      env['REQUEST_METHOD'] = handler.command
      if '?' in handler.path:
        path, query = handler.path.split('?', 1)
      else:
        path, query = handler.path, ''
      ownPath=self.prefix
      mpath=urllib.parse.unquote(path, 'iso-8859-1')[len(ownPath):]
      env['PATH_INFO'] = mpath
      env['QUERY_STRING'] = query

      host = handler.address_string()
      if host != handler.client_address[0]:
        env['REMOTE_HOST'] = host
      env['REMOTE_ADDR'] = handler.client_address[0]

      if handler.headers.get('content-type') is None:
        env['CONTENT_TYPE'] = handler.headers.get_content_type()
      else:
        env['CONTENT_TYPE'] = handler.headers['content-type']

      length = handler.headers.get('content-length')
      if length:
        env['CONTENT_LENGTH'] = length

      for k, v in handler.headers.items():
        k = k.replace('-', '_').upper()
        v = v.strip()
        if k in env:
          continue  # skip content length, type,etc.
        if 'HTTP_' + k in env:
          env['HTTP_' + k] += ',' + v  # comma-separate multiple headers
        else:
          env['HTTP_' + k] = v
      return env

  def handleRequest(self,url,handler,args):
    if self.mapproxy is None:
      self.logger.error("request %s, mapproxy not created",url)
      raise Exception("mapproxy not created")
    stderr = io.StringIO()
    try:
      shandler = OwnWsgiHandler(
        handler.rfile, handler.wfile, stderr, self._getWsgiEnv(handler)
      )
      shandler.request_handler = handler  # backpointer for logging
      shandler.log_request = handler.log_request
      shandler.run(self.mapproxy)
    finally:
      errors = stderr.getvalue()
      if len(errors) > 0:
        self.logger.error("request %s : %s", url, errors)