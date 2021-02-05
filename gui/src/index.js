/*
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
*/
import '../style/index.less';
import 'leaflet/dist/leaflet.css';
import 'leaflet-draw/dist/leaflet.draw.css';
import L from 'leaflet';
import 'leaflet-draw';
import {getBoundsFromSelections, getIntersectionBounds, tileCountForBounds} from "./map";
import {buttonEnable, safeName, showHideOverlay, forEach, setCloseOverlayActions, showSelectOverlay} from "./util";
(function(){
    let selectedLayer=undefined;
    let base=window.location.href.replace(/mapproxy\/gui.*/,'mapproxy');
    let map=undefined;
    let drawnItems = undefined;
    let flask;
    let apiRequest=function(command){
        let url=base+"/api/"+command;
        return new Promise(function(resolve,reject){
            fetch(url)
            .then(function(r){
                return r.json();
            })
            .then(function(data){
                if (! data.status || data.status !== 'OK'){
                    reject("status: "+data.status);
                    retturn;
                }
                resolve(data);
                return;
            })
            .catch(function(error){
                reject(error);
            });
        });
    }



    let ignoreNextChanged=false;
    let codeChanged=function(changed){
        buttonEnable('saveEditOverlay',changed && ! ignoreNextChanged);
        ignoreNextChanged=false;
    }
    let showError=function(error){
        alert(error);
    }
    let showEdit=function(){
        showHideOverlay('editOverlay',true);
        fetch(base+'/api/getConfig')
        .then(function(resp){
            return resp.text();
        })
        .then(function(text){
            if (flask) flask.updateCode(text);
            codeChanged(false);
            ignoreNextChanged=true;
        })
        .catch(function(error){
            showError(error);
        })
    }

    let saveConfig=function(){
        if (! flask) return;
        let data=flask.getCode();
        try{
            //validate data
        }catch(e){
            showError("internal error: "+e);
            return;
        }
        if (confirm("Really overwrite config")){
            fetch(base+'/api/uploadConfig',{
                method: 'POST',
                headers:{
                    'Content-Type':'text/plain'
                },
                body: data
            })
            .then(function(resp){
                return resp.json();
            })
            .then(function(result){
                if (! result.status || result.status !== 'OK'){
                    showError(result.status);
                    return;
                }
                showHideOverlay('editOverlay',false);
            })
            .catch(function(error){
                showError(error);
            })
            return ;
        }
    }

    let saveSelections=function(seedFor){
        let name="default";
        let ne=document.getElementById('selectionName');
        if (ne) name=ne.value;
        let bounds=getBoundsFromSelections(drawnItems);
        let numTiles=0;
        let z=map.getZoom();
        let alreadyCounted=[];
        //tile counting - only for mode current zoom
        bounds.forEach(function(bound){
            let maxTiles=tileCountForBounds(map,bound,z);
            //subtract intersections
            alreadyCounted.forEach(function(other){
                let intersect=getIntersectionBounds(bound,other);
                if (intersect){
                    let intersectNum=tileCountForBounds(map,intersect,z);
                    maxTiles-=intersectNum;
                    if (maxTiles < 0) maxTiles=0; //hmmm
                }
            })
            numTiles+=maxTiles;
            alreadyCounted.push(bound);
        })
        name=safeName(name);
        let url="saveSelection?data="+
            encodeURIComponent(JSON.stringify(bounds))+
            "&name="+encodeURIComponent(name);
        if (seedFor){
            url+="&startSeed="+encodeURIComponent(selectedLayer);
        }
        apiRequest(url
        )
        .then((res)=>{
            if (res.numTiles !== undefined){
                alert("seed started with "+res.numTiles+" tiles");
            }
        })
        .catch((e)=>showError(e));
    }
    let startSeed=()=>{
        saveSelections(true);
    }
    let showSelection=(name)=>{
        apiRequest('loadSelection?name='+encodeURIComponent(name))
            .then((data)=>{
                let ne=document.getElementById('selectionName');
                if (ne) ne.value=name;
                drawnItems.clearLayers();
                for (let i in data.data){
                    let box=data.data[i];
                    let rect=L.rectangle([L.latLng(box._southWest),L.latLng(box._northEast)]);
                    drawnItems.addLayer(rect);
                }
                updateTileCount();
            })
            .catch((e)=>showError(e));
    };
    let loadSelection=()=>{
        apiRequest('listSelections')
            .then((data)=>{
                showSelectOverlay(data.data,"load selection")
                    .then((selected)=>showSelection(selected))
                    .catch(()=>{})
            })
            .catch((e)=>showError(e));
    }
    let deleteSelection=()=>{
        apiRequest('listSelections')
            .then((data)=>{
                showSelectOverlay(data.data,"delete selection")
                    .then((selected)=>{
                        apiRequest('deleteSelection?name='+encodeURIComponent(selected))
                            .then(()=>{})
                            .catch((e)=>showError(e))
                    })
                    .catch(()=>{})
            })
            .catch((e)=>showError(e));
    }
    let updateTileCount=()=>{
        let te=document.getElementById('numTiles');
        if (! te) return;
        te.classList.add('blink');
        let bounds=getBoundsFromSelections(drawnItems);
        apiRequest('countTiles?data='+encodeURIComponent(JSON.stringify(bounds)))
            .then((resp)=>{
                te.classList.remove('blink');
                if (resp.numTiles > resp.allowed){
                    te.classList.add('textError')
                }
                else{
                    te.classList.remove('textError');
                }
                te.textContent=resp.numTiles;
            })
            .catch((e)=>showError(e));
    }
    let updateZoom=()=>{
        let zoomInfo=document.getElementById('currentZoom');
        if (! zoomInfo) return;
        zoomInfo.textContent=map.getZoom();
    }
    let buttonActions={
        save:()=>saveSelections(false),
        loadSelection: loadSelection,
        deleteSelection:deleteSelection,
        startSeed: startSeed
    }
    let selectTab=function(id){
        forEach(document.querySelectorAll('.tab'),function(i,tab){
            tab.classList.remove('active');
        })
        forEach(document.querySelectorAll('.tabSelect .selector'),function(i,tab){
            if (tab.getAttribute('data-tabid') === id){
                tab.classList.add('active');
            }
            else {
                tab.classList.remove('active');
            }
        })
        forEach(document.querySelectorAll('#'+id),function(i,tab){
            tab.classList.add('active');
        })
        map.invalidateSize();
    }
    window.addEventListener('load',function(){
        let title=document.getElementById('title');
        if (window.location.search.match(/title=no/)){
            if (title) title.style.display="none";
        }
        let demo=document.getElementById('demoFrame');
        if (demo) {
            demo.setAttribute('src',base+"/api/mapproxy/demo/");
        }
        forEach(document.querySelectorAll('button'),
            function(i,bt) {
                let handler = buttonActions[bt.getAttribute('id')] ||
                    buttonActions[bt.getAttribute('name')];
                if (handler) {
                    bt.addEventListener('click', handler);
                }
            });
        forEach(document.querySelectorAll('.tabSelect .selector'),
            function (i,sel){
                sel.addEventListener('click',function(ev){
                    ev.preventDefault();
                    let id=ev.target.getAttribute('data-tabid');
                    if (id) selectTab(id);
                })
            });
        setCloseOverlayActions();
        flask=new CodeFlask('#editOverlay .overlayContent',{
            language: 'markup',
            lineNumbers: true,
            defaultTheme: false
        });
        flask.onUpdate(function(){codeChanged(true)});
        let networkState=document.getElementById('networkStatus');
        let selName=document.getElementById('selectionName');
        let d=new Date()
        if (selName) selName.value="selection-"+d.getFullYear()+"-"+d.getMonth()+"-"+d.getDate();
        let first=true;
        this.window.setInterval(function(){
            let canSave=drawnItems.getLayers().length > 0;
            forEach(document.querySelectorAll('button.withSelections'),(i,bt)=>{
                buttonEnable(bt,canSave);
            });
            let url='status';
            apiRequest(url)
            .then(function(data){
                if (networkState){
                    let newState='unknown';
                    if (data.network !== undefined){
                        if (data.network) newState='ok';
                        else newState='error';
                    }
                    if (! networkState.classList.contains(newState)){
                        let states=['unknown','error','ok'];
                        states.forEach(function(state){
                            if (state !== newState){
                                networkState.classList.remove(state);
                            }
                            else{
                                networkState.classList.add(state);
                            }
                        });
                    }
                }

            })
            .catch(function(error){
                console.log(error);
            })
        },1000);
        map=L.map('map').setView([54,13],6);
        drawnItems=new L.FeatureGroup();
        map.addLayer(drawnItems);
        updateZoom();

        let drawControl = new L.Control.Draw({
            position: 'topright',
            draw: {
                polyline: false,
                polygon: false,
                circle: false,
                circlemarker: false,
                marker: false,
                rectangle: {
                    shapeOptions: {
                        clickable: true
                    }
                }
            },
            edit: {
                featureGroup: drawnItems,
                remove: true
            }
        });
        map.addControl(drawControl);
        map.on(L.Draw.Event.CREATED, function (e) {
            let layer = e.layer;
            drawnItems.addLayer(layer);
            updateTileCount();
        });
        map.on(L.Draw.Event.DELETED,updateTileCount);
        map.on(L.Draw.Event.EDITED,updateTileCount);
        map.on('zoomend',updateZoom)
        let layers={};
        apiRequest('layers')
            .then(function(resp){
                if (resp && resp.data && resp.data.base){
                    let cfg=resp.data.base;
                    let name=cfg.name;
                    let url=cfg.url;
                    let layer = L.tileLayer(url+'/{z}/{x}/{y}.png',{
                        });
                    layer.addTo(map);
                }
                if (resp && resp.data){
                    let layerList=document.getElementById('layerFrame');
                    if (layerList){
                        layerList.innerText='';
                        let first=true;
                        for (let lname in resp.data) {
                            if (lname === 'base') continue;
                            let lconfig = resp.data[lname];
                            let item = document.createElement('div');
                            item.classList.add('layerSelect');
                            let rb = document.createElement('input');
                            rb.setAttribute('type', 'radio');
                            rb.setAttribute('name', 'layer');
                            if (first) {
                                rb.checked = true;
                                selectedLayer=lname;
                            }
                            let layer=L.tileLayer(lconfig.url+'/{z}/{x}/{y}.png');
                            layers[lname]=layer;
                            if (first) map.addLayer(layer);
                            rb.setAttribute('value',lname);
                            rb.addEventListener('change',function(){
                                forEach(layerList.querySelectorAll('input[type="radio"]'),
                                    function(idx,el){
                                    let layer=layers[el.getAttribute('value')];
                                    if (layer) {
                                        if (el.checked) {
                                            map.addLayer(layer);
                                            selectedLayer=el.getAttribute('value');
                                        }
                                        else map.removeLayer(layer);
                                    }
                                    })
                                map.invalidateSize();
                            });
                            first=false;
                            item.appendChild(rb);
                            let label = document.createElement('span');
                            label.innerText = lconfig.name;
                            item.appendChild(label);
                            layerList.appendChild(item);
                        }
                    }
                }
            })
            .catch(function(error){
                showError(error);
            })
        selectTab('statustab');
    })
})();