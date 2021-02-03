#! /bin/sh
#package build using https://github.com/goreleaser/nfpm on docker
err(){
  echo "ERROR: $*"
  exit 1
}
pdir=`dirname $0`
pdir=`readlink -f "$pdir"`
boxesRepo='https://raw.githubusercontent.com/free-x/mbtiles-nautical-boxes/contrib/iho/contrib/iho'
boxes="allcountries.bbox"
buildDir="$pdir/build/boxes"
#set -x
config=package.yaml
force=0
if [ "$1" = "-f" ] ; then
  force=1
  shift
fi  
version="$1"
if [ "$version" = "" ] ; then
  version=`date '+%Y%m%d'`
fi
echo loading/checking boxes
if [ ! -d "$buildDir" ]; then
  mkdir -p "$buildDir" || err unable to create $buildDir
fi
for box in `echo $boxes`
do
  bf="$buildDir/$box"
  if [ ! -f "$bf" -o $force = 1 ]; then
    url="$boxesRepo/$box"
    echo downloading "$url"
    curl -o "$bf" -f "$url" || err unable to download "$url"
  fi
done
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
