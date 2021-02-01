import io
import os
import shutil
import time
import traceback
import urllib.parse
from wsgiref.headers import Headers
from simple_server import ServerHandler
from mapproxy.wsgiapp import make_wsgi_app
from xml.sax.saxutils import escape

NAME="mapproxy"

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



class Plugin:
  BASE_CONFIG='avnav_base.yaml'
  USER_CONFIG='avnav_user.yaml'
  NAME_PREFIX='mp-'
  MPREFIX="mapproxy"
  ICONFILE="logo.png"
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
    self.queryPeriod=5



  def getConfigValue(self,name):
    defaults=self.pluginInfo()['config']
    for cf in defaults:
      if cf['name'] == name:
        return self.api.getConfigValue(name,cf.get('default'))
    return self.api.getConfigValue(name)

  def createMapProxy(self):
    configFile=os.path.join(self.dataDir,self.BASE_CONFIG)
    self.api.setStatus('INACTIVE','creating mapproxy with config %s'%configFile)
    self.mapproxy = make_wsgi_app(configFile,ignore_config_warnings=False, reloader=True)
    self.api.log("created mapproxy wsgi app")

  def getMaps(self):
    rt=[]
    if self.mapproxy is None or self.mapproxy.app is None:
      self.api.debug("mapproxy not initialized in getMaps")
      return rt
    handlers=self.mapproxy.app.handlers
    if handlers is None or handlers.get('tiles') is None:
      self.api.debug("no tiles service in mapproxy in getMaps")
      return rt
    tiles=handlers['tiles']
    internalPath=self.MPREFIX+"/tiles/1.0.0"
    chartBase=self.api.getBaseUrl()+"/api/"+internalPath
    iconUrl=self.api.getBaseUrl()+"/"+self.ICONFILE
    for k,v in tiles.layers.items():
      internals={'path':internalPath+"/"+k[0]+"/"+k[1]}
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
        self.api.debug("unable to fetch internals for layer: %s",str(e))
      entry={
        'name': self.NAME_PREFIX+k[0],
        'url': chartBase+"/"+k[0]+"/"+k[1],
        'icon': iconUrl,
        'sequence':self.sequence,
        'internal':internals
      }
      rt.append(entry)
    self.charts=rt
    return rt

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
      self.dataDir=self.getConfigValue('dataDir')
      if self.dataDir is not None:
        self.dataDir=self.dataDir.replace('$DATADIR',avnavData)
      else:
        self.dataDir=os.path.join(avnavData,'mapproxy')
      if not os.path.exists(self.dataDir):
        os.makedirs(self.dataDir)
      if not os.path.isdir(self.dataDir):
        raise Exception("unable to create data directory %s"%self.dataDir)
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
      self.createMapProxy()
      # we register an handler for API requests
      self.api.registerRequestHandler(self.handleApiRequest)
      self.api.registerUserApp(self.api.getBaseUrl() + "/api/mapproxy/demo/", "logo.png")
      self.api.registerChartProvider(self.listCharts)
      self.queryPeriod=int(self.getConfigValue('chartQueryPeriod'))
    except Exception as e:
      self.api.error("error in startup: %s",traceback.format_exc())
      self.api.setStatus("ERROR","exception in startup: %s"%str(e))
      return
    self.api.log("started")
    self.api.setStatus("NMEA","successfully started")
    while True:
      try:
        self.getMaps()
      except Exception as e:
        self.api.debug("error in main loop: %s",traceback.format_exc())
      time.sleep(self.queryPeriod)


  def getWsgiEnv(self,handler):
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
      ownPath=self.api.getBaseUrl()+"/api/"+self.MPREFIX
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
        k = k.replace('-', '_').upper();
        v = v.strip()
        if k in env:
          continue  # skip content length, type,etc.
        if 'HTTP_' + k in env:
          env['HTTP_' + k] += ',' + v  # comma-separate multiple headers
        else:
          env['HTTP_' + k] = v
      return env

  def _findChartEntry(self,path):
    for ce in self.charts:
      internals=ce.get('internal')
      if internals is None:
        continue
      if internals.get('path') == path:
        return ce


  def handleApiRequest(self,url,handler,args):
    """
    handler for API requests send from the JS
    @param url: the url after the plugin base
    @param handler: the HTTP request handler
                    https://docs.python.org/2/library/basehttpserver.html#BaseHTTPServer.BaseHTTPRequestHandler
    @param args: dictionary of query arguments
    @return:
    """
    if url == 'status':
      return {'status': 'OK',
              }
    if url == 'charts':
      return {
        'status':'OK',
      }
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
      stderr=io.StringIO()
      try:
        shandler = OwnWsgiHandler(
          handler.rfile, handler.wfile, stderr, self.getWsgiEnv(handler)
        )
        shandler.request_handler = handler  # backpointer for logging
        shandler.log_request=handler.log_request
        shandler.run(self.mapproxy)
      finally:
        errors=stderr.getvalue()
        if len(errors) > 0:
          self.api.error("request %s : %s",url,errors)
    return {'status','unknown request'}


