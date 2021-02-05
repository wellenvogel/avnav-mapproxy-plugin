#! /usr/bin/env python3
import os
import sys
import time

import yaml
sys.path.insert(0,os.path.join(os.path.dirname(__file__),'..'))
print("path=%s"%sys.path)

import seed_runner


class Log(object):
  def log(self,fmt,*args):
    print("I:%s"%(fmt%args))
  def debug(self,fmt,*args):
    print("D:%s"%(fmt%args))
  def error(self,fmt,*args):
    print("E:%s"%(fmt%args))
runner=seed_runner.SeedRunner(sys.argv[1],sys.argv[2],logHandler=Log())
with open(sys.argv[3],"r") as cfg:
  seedConfig=yaml.safe_load(cfg)
rt=runner.runSeed(seedConfig)

count=0
while True:
  count+=1
  st=runner.checkRunning()
  print("run status: %s"%str(st))
  print("status: %s"%runner.seedStatus)
  print("info: %s"%runner.info)
  if not st:
    break
  if len(sys.argv) > 4:
    if count == int(sys.argv[4]):
      print("try second start")
      runner.runSeed(seedConfig)
  time.sleep(1)

runner.cleanupLogs()