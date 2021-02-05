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
import io
import os
import traceback
import urllib.parse
from wsgiref.headers import Headers
from wsgiref.simple_server import ServerHandler
from mapproxy.wsgiapp import make_wsgi_app


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

class MapProxyWrapper(object):

  def __init__(self,prefix,configFile,logger):
    self.prefix=prefix
    self.configFile=configFile
    logger.log("creating mapproxy wsgi app with config %s",configFile)
    self.mapproxy = make_wsgi_app(configFile, ignore_config_warnings=False, reloader=True)
    logger.log("created mapproxy wsgi app")
    self.logger=logger

  def getMaps(self):
    rt=[]
    if self.mapproxy is None or self.mapproxy.app is None:
      self.logger.debug("mapproxy not initialized in getMaps")
      return rt
    handlers=self.mapproxy.app.handlers
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

  def getMappings(self,raiseError=False):
    from mapproxy.config.loader import load_configuration_file
    config = {}
    if not os.path.exists(self.configFile):
      return {}
    dir = os.path.dirname(self.configFile)
    fname = os.path.basename(self.configFile)
    try:
      config = load_configuration_file([fname], dir)
    except Exception as e:
      self.logger.debug("Error reading config from %s: %s", self.configFile, traceback.format_exc())
      if raiseError:
        raise
    layer2caches = {}
    layers = config.get('layers')
    caches = config.get('caches')
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
            if layer2caches.get(name) is None:
              layer2caches[name] = []
            layer2caches[name].append(s)
    return layer2caches

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