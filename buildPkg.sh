#! /bin/sh
#package build using https://github.com/goreleaser/nfpm on docker
err(){
  echo "ERROR: $*"
  exit 1
}
pdir=`dirname $0`
pdir=`readlink -f "$pdir"`
cd $pdir
#set -x
config=package.yaml
force=0
incremental=0
while getopts fi opt
do
  case "$opt" in
    f) force=1
      ;;
    i) incremental=1
      ;;
    ?) err invalid option $opt
      ;;  
  esac      
done
shift $((OPTIND-1))
version="$1"
if [ "$version" = "" ] ; then
  version=`date '+%Y%m%d'`
fi
if [ $incremental != 1 ];then
  echo npm install
  ( cd gui && npm install ) || err error in npm install
fi
(cd gui && npm run production ) || err building gui
echo building version $version
tmpf=package$$.yaml
rm -f $tmpf
sed "s/^ *version:.*/version: \"$version\"/" $config > $tmpf
config=$tmpf
docker run  --rm   -v "$pdir":/tmp/pkg   --user `id -u`:`id -g` -w /tmp/pkg wellenvogel/nfpm:1.0 pkg -p deb -f $config
rt=$?
if [ "$tmpf" != "" ] ; then
  rm -f $tmpf
fi
exit $rt
