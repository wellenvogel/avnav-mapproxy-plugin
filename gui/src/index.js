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
import '../style/index.css';
import 'leaflet/dist/leaflet.css';
import 'leaflet-draw/dist/leaflet.draw.css';
import L from 'leaflet';
import 'leaflet-draw';
import {getBoundsFromSelections, getIntersectionBounds, tileCountForBounds} from "./map";
import {buttonEnable, showHideOverlay} from "./util";
(function(){
    let base=window.location.href.replace(/mapproxy\/gui.*/,'mapproxy');
    let map=undefined;
    let drawnItems = undefined;
    const forEach = function (array, callback, scope) {
        for (let i = 0; i < array.length; i++) {
            callback.call(scope, i, array[i]); // passes back stuff we need
        }
    };
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

    let saveSelections=function(){
        let name="default";
        let ne=document.getElementById('selectionName');
        if (ne) name=ne.value;
        let bounds=getBoundsFromSelections(drawnItems);
        let numTiles=0;
        let z=map.getZoom();
        let alreadyCounted=[];
        bounds.forEach(function(bound){
            let maxTiles=tileCountForBounds(map,bound,z);
            //subtract intersections
            alreadyCounted.forEach(function(other){
                let intersect=getIntersectionBounds(bound,other);
                if (intersect){
                    let intersectNum=tileCountForBounds(intersect,z);
                    maxTiles-=intersectNum;
                    if (maxTiles < 0) maxTiles=0; //hmmm
                }
            })
            numTiles+=maxTiles;
            alreadyCounted.push(bound);
        })
        apiRequest("saveBoxes?data="+encodeURIComponent(JSON.stringify(bounds)))
        .then((res)=>{
                alert("saved to "+name+", "+numTiles+" tiles on current zoom "+z);
        })
        .catch((e)=>showError(e));
    }
    let buttonActions={
        save:saveSelections
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
        });
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
                            if (first) rb.checked = true;
                            let layer=L.tileLayer(lconfig.url+'/{z}/{x}/{y}.png');
                            layers[lname]=layer;
                            if (first) map.addLayer(layer);
                            rb.setAttribute('value',lname);
                            rb.addEventListener('change',function(){
                                forEach(layerList.querySelectorAll('input[type="radio"]'),
                                    function(idx,el){
                                    let layer=layers[el.getAttribute('value')];
                                    if (layer) {
                                        if (el.checked) map.addLayer(layer);
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