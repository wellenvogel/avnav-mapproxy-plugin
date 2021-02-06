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
import '../lib/codeflask.css';
import SeedMap from "./map";
import Prismjs from 'prismjs';
import CodeFlask from "codeflask";
import yaml from 'js-yaml';
import FileDownload from 'js-file-download';
import {
    buttonEnable,
    safeName,
    showHideOverlay,
    setCloseOverlayActions,
    showSelectOverlay,
    setStateDisplay, setTextContent, apiRequest, showError, forEachEl, getDateString
} from "./util";
(function(){
    let activeTab=undefined;
    let base=window.location.href.replace(/mapproxy\/gui.*/,'mapproxy');
    let map=undefined;
    let flask;
    let ignoreNextChanged=false;
    let lastSequence=undefined;
    let codeChanged=function(changed){
        buttonEnable('saveEditOverlay',changed && ! ignoreNextChanged);
        ignoreNextChanged=false;
    }
    let getAndCheckConfig=()=>{
        if (! flask) return;
        let data=flask.getCode();
        let o;
        try{
            o=yaml.load(data,{schema:yaml.JSON_SCHEMA});
        }catch(e){
            showError("yaml error: "+e);
            return;
        }
        return data
    }
    let downloadConfig=(filename)=>{
        if (! filename) filename="avnav_user"+getDateString()+".yaml";
        let data=getAndCheckConfig();
        if (! data) return;
        FileDownload(data,filename);
    }
    let saveConfig=function(){
        let data=getAndCheckConfig();
        if (! data) return;
        if (confirm("Really overwrite config?")){
            apiRequest(base,'saveConfig?data='+encodeURIComponent(data))
            .then((result)=>{
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
        let bounds=map.getSelectionBounds();
        name=safeName(name);
        let url="saveSelection?data="+
            encodeURIComponent(JSON.stringify(bounds))+
            "&name="+encodeURIComponent(name);
        if (seedFor){
            url+="&startSeed="+encodeURIComponent(map.getSelectedLayer());
        }
        apiRequest(base,url
        )
        .then((res)=>{
            showHideOverlay('spinnerOverlay',false);
            if (res.numTiles !== undefined){
                showToast("seed started with "+res.numTiles+" tiles");
            }
        })
        .catch((e)=>{
            showHideOverlay('spinnerOverlay',false);
            showError(e);
        });
    }
    let startSeed=()=>{
        showHideOverlay('spinnerOverlay',true)
        saveSelections(true);
    }
    let showSelection=(name)=>{
        apiRequest(base,'loadSelection?name='+encodeURIComponent(name))
            .then((data)=>{
                setTextContent('#selectionName',name);
                map.setSelections(data.data);
            })
            .catch((e)=>showError(e));
    };
    let loadSelection=()=>{
        apiRequest(base,'listSelections')
            .then((data)=>{
                showSelectOverlay(data.data,"load selection")
                    .then((selected)=>showSelection(selected))
                    .catch(()=>{})
            })
            .catch((e)=>showError(e));
    }
    let deleteSelection=()=>{
        apiRequest(base,'listSelections')
            .then((data)=>{
                showSelectOverlay(data.data,"delete selection")
                    .then((selected)=>{
                        apiRequest(base,'deleteSelection?name='+encodeURIComponent(selected))
                            .then(()=>{})
                            .catch((e)=>showError(e))
                    })
                    .catch(()=>{})
            })
            .catch((e)=>showError(e));
    }
    let stopSeed=()=>{
        apiRequest(base,'killSeed')
            .then(()=>{})
            .catch((e)=>showError(e));
    }
    let showLog=()=>{
        fetch(base+"/api/getLog").then((resp)=>resp.text())
            .then((txt)=>{
                let logel=document.querySelector('#logOverlay .overlayContent');
                if (! logel) return;
                logel.textContent=txt;
                logel.scrollTop=logel.scrollHeight;
                showHideOverlay('logOverlay',true)
            })
            .catch((e)=>showError(e))
    }
    let editConfig=()=>{
        apiRequest(base,'loadConfig')
            .then((data)=>{
                if (flask) flask.updateCode(data.data);
                codeChanged(false);
                ignoreNextChanged=true;
                showHideOverlay('editOverlay',true);
            })
            .catch((e)=>showError(e));
    }
    let buttonActions={
        checkEditOverlay: getAndCheckConfig,
        downloadEditOverlay: ()=>downloadConfig(),
        saveEditOverlay: saveConfig,
        editConfig:editConfig,
        showLog: showLog,
        reloadLog: showLog,
        killSeed: stopSeed,
        stopSeed: stopSeed,
        save:()=>saveSelections(false),
        loadSelection: loadSelection,
        deleteSelection:deleteSelection,
        startSeed: startSeed
    }
    let updateLayers=()=>{
        if (activeTab === 'downloadtab') map.loadLayers('layerFrame');
        else {
            if (activeTab === 'statustab') {
                setTextContent('#statusLayers','');
                let parent=document.getElementById('statusLayers');
                if (! parent) return;
                apiRequest(base, 'layers')
                    .then((data) => {
                        if (! data.data) return;
                        for (let i in data.data){
                            let layer=data.data[i];
                            let lf=document.createElement('div');
                            lf.classList.add('layerInfo');
                            let ln=document.createElement('span');
                            ln.classList.add('label');
                            ln.textContent='Layer:'
                            lf.appendChild(ln);
                            ln=document.createElement('span');
                            ln.classList.add('value');
                            ln.textContent=layer.name;
                            lf.appendChild(ln);
                            parent.appendChild(lf);
                        }
                    })
                    .catch((e) => showError(e));
            }
        }
    }

    let selectTab=function(id){
        forEachEl('.tab',(tab)=>{
            tab.classList.remove('active');
        })
        forEachEl('.tabSelect .selector',(tab)=>{
            if (tab.getAttribute('data-tabid') === id){
                tab.classList.add('active');
            }
            else {
                tab.classList.remove('active');
            }
        })
        forEachEl('#'+id,(tab)=>{
            tab.classList.add('active');
        })
        activeTab=id;
        updateLayers();
    }
    window.addEventListener('load',function(){
        let title=document.getElementById('title');
        if (window.location.search.match(/title=no/)){
            if (title) title.style.display="none";
        }
        let toast=document.getElementById('toast');
        if (toast){
            toast.addEventListener('click',()=>showHideOverlay('toast'))
        }
        let demo=document.getElementById('demoFrame');
        if (demo) {
            demo.setAttribute('src',base+"/api/mapproxy/demo/");
        }
        forEachEl('button',(bt)=> {
                let handler = buttonActions[bt.getAttribute('id')] ||
                    buttonActions[bt.getAttribute('name')];
                if (handler) {
                    bt.addEventListener('click', handler);
                }
            });
        forEachEl('.tabSelect .selector',(sel)=>{
                sel.addEventListener('click',function(ev){
                    ev.preventDefault();
                    let id=ev.target.getAttribute('data-tabid');
                    if (id) selectTab(id);
                })
            });
        setCloseOverlayActions();
        flask=new CodeFlask('#editOverlay .overlayContent',{
            language: 'yaml',
            lineNumbers: true,
            defaultTheme: false
        });
        flask.addLanguage('yaml',Prismjs.languages['yaml']);
        flask.onUpdate(function(){codeChanged(true)});
        let networkState=document.getElementById('networkStatus');
        let selName=document.getElementById('selectionName');
        let d=new Date()
        if (selName) selName.value="selection-"+getDateString();
        let first=true;
        this.window.setInterval(function () {
            let canSave = map && map.hasDrawnItems();
            let url = 'status';
            apiRequest(base,url)
                .then(function (data) {
                    setStateDisplay('.networkState', data.network);
                    let seed=data.seed || {};
                    let seedStatus=seed.status;
                    let mapproxy=data.mapproxy||{};
                    setStateDisplay('.seedStatus',seedStatus);
                    setStateDisplay('.proxyStatus',mapproxy.status);
                    setTextContent('.proxySequence', (! mapproxy.lastError)?
                        "sequence "+parseInt(data.sequence):'');
                    setTextContent('.proxyError',mapproxy.lastError);

                    buttonEnable('startSeed',seedStatus !== 'running' && canSave);
                    buttonEnable('killSeed',seedStatus === 'running');
                    buttonEnable('showLog',seed.logFile);
                    let name=seed.name||'';
                    if (name instanceof Array) name=name.join(',');
                    name=(seed.selection||'')+' '+name;
                    setTextContent('.seedInfo',name+" "+(data.seed || {}).info)
                    forEachEl('#stopSeed',(el)=>{
                        el.style.display=(seedStatus === 'running')?'inline-block':'none'
                    })
                    if (data.sequence !== lastSequence){
                        if (lastSequence !== undefined) updateLayers();
                        lastSequence=data.sequence;
                    }
                })
                .catch(function (error) {
                    console.log(error);
                })
        }, 1000);
        map=new SeedMap('map',base);
        selectTab('statustab');
    })
})();