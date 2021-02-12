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
import os
import sys

import yaml


def loadModuleFromFile(fileName,namePrefix=None):
  if not os.path.isabs(fileName):
    fileName=os.path.join(os.path.dirname(__file__),fileName)
  moduleName=os.path.splitext(os.path.basename(fileName))[0]
  if namePrefix is not None:
    moduleName=namePrefix+moduleName
  # see https://docs.python.org/3/library/importlib.html#module-importlib
  spec = importlib.util.spec_from_file_location(moduleName, fileName)
  module = importlib.util.module_from_spec(spec)
  spec.loader.exec_module(module)
  sys.modules[moduleName] = module
  return module

class InjectorException(Exception):
  pass

class Injector(object):
  def __init__(self,configDir):
    self.configDir=configDir
    self.originalHttpClient=None
    self.creationException=None
    try:
      import mapproxy.config.loader
      source=mapproxy.config.loader.SourceConfiguration
      self.originalHttpClient=source.http_client
      def httpClientWrapper(*args):
        rt=self.originalHttpClient(*args)
        self._createOpenWarpper(args[0],rt[0])
        return rt
      source.http_client=httpClientWrapper

      import mapproxy.source
      def offlineGetMap(*args):
        raise Exception("offline")
      mapproxy.source.DummySource.get_map=offlineGetMap
    except Exception as e:
      self.creationException=e

  def checkCreatedIfNeeded(self,configFile):
    '''
    we only check if we really can inject some
    plugin if the config really needs this
    so if mapproxy will change we can at least
    run normal sources without plugins
    :param configFile:
    :return:
    '''
    with open(configFile,"r") as fh:
      config=yaml.safe_load(fh)
    if not 'sources' in config:
      return
    for name,src in config['sources'].items():
      if src.get('plugin') is not None:
        if self.originalHttpClient is None:
          if self.creationException:
            raise InjectorException("unable to inject plugin for %s, not initialized: %s"%
                                    (name,str(self.creationException)))
          raise InjectorException("unable to inject plugin for %s ,injector not initialized"%name)

  def _createOpenWarpper(self,source,httpClient):
    originalOpen = httpClient.open
    client=httpClient
    plugin=source.conf.get('plugin')
    if plugin is None:
      return
    if not os.path.isabs(plugin):
      plugin=os.path.join(self.configDir,plugin)
    if not os.path.exists(plugin):
      raise InjectorException("plugin %s not found"%plugin)
    pluginModule=loadModuleFromFile(plugin,'injector-')
    prepareMethod=None
    if hasattr(pluginModule,'prepareRequest'):
      prepareMethod=pluginModule.prepareRequest
    checkResponse=None
    if hasattr(pluginModule,'checkResponse'):
      checkResponse=pluginModule.checkResponse
    if checkResponse is None and prepareMethod is None:
      raise InjectorException("either prepareRequest or checkResponse must be defined in %s"%plugin)
    #convert header_list to dict to make it modifyable
    headers={}
    if type(client.header_list) is list:
      pass
    else:
      headers.update(client.header_list)
    def openWrapper(*args, **kwargs):
      import mapproxy.layer
      try:
        if prepareMethod is not None:
          url=prepareMethod(args[0],headers)
          if url is None:
            url=args[0]
        else:
          url=args[0]
        client.header_list = headers.items()
        rt = originalOpen(url, **kwargs)
        if checkResponse is not None:
          rs=checkResponse(rt,url)
          if rs is None:
            raise mapproxy.layer.BlankImage()
          rt=rs
        return rt
      except Exception as e:
          raise
    httpClient.open = openWrapper