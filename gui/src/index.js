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
import SeedMap from "./map";
import {
    buttonEnable,
    safeName,
    showHideOverlay,
    setCloseOverlayActions,
    showSelectOverlay,
    setStateDisplay, setTextContent, apiRequest, showError, forEachEl
} from "./util";
(function(){
    let selectedLayer=undefined;
    let base=window.location.href.replace(/mapproxy\/gui.*/,'mapproxy');
    let map=undefined;
    let flask;
    let ignoreNextChanged=false;
    let codeChanged=function(changed){
        buttonEnable('saveEditOverlay',changed && ! ignoreNextChanged);
        ignoreNextChanged=false;
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
        let bounds=map.getSelectionBounds();
        name=safeName(name);
        let url="saveSelection?data="+
            encodeURIComponent(JSON.stringify(bounds))+
            "&name="+encodeURIComponent(name);
        if (seedFor){
            url+="&startSeed="+encodeURIComponent(selectedLayer);
        }
        apiRequest(base,url
        )
        .then((res)=>{
            showHideOverlay('spinnerOverlay',false);
            if (res.numTiles !== undefined){
                alert("seed started with "+res.numTiles+" tiles");
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
    let buttonActions={
        showLog: showLog,
        reloadLog: showLog,
        killSeed: stopSeed,
        stopSeed: stopSeed,
        save:()=>saveSelections(false),
        loadSelection: loadSelection,
        deleteSelection:deleteSelection,
        startSeed: startSeed
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
        if (id === 'downloadtab') map.loadLayers('layerFrame');
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
            language: 'markup',
            lineNumbers: true,
            defaultTheme: false
        });
        flask.onUpdate(function(){codeChanged(true)});
        let networkState=document.getElementById('networkStatus');
        let selName=document.getElementById('selectionName');
        let d=new Date()
        if (selName) selName.value="selection-"+d.getFullYear()+"-"+(d.getMonth()+1)+"-"+d.getDate();
        let first=true;
        this.window.setInterval(function () {
            let canSave = map && map.hasDrawnItems();
            let url = 'status';
            apiRequest(base,url)
                .then(function (data) {
                    setStateDisplay('.networkState', data.network);
                    let seedStatus=(data.seed || {}).status;
                    setStateDisplay('.seedStatus',seedStatus)
                    buttonEnable('startSeed',seedStatus !== 'running' && canSave);
                    buttonEnable('killSeed',seedStatus === 'running');
                    buttonEnable('showLog',(data.seed||{}).logFile);
                    let name=(data.seed || {}).name||'';
                    if (name instanceof Array) name=name.join(',');
                    setTextContent('.seedInfo',name+" "+(data.seed || {}).info)
                    forEachEl('#stopSeed',(el)=>{
                        el.style.display=(seedStatus === 'running')?'inline-block':'none'
                    })
                })
                .catch(function (error) {
                    console.log(error);
                })
        }, 1000);
        map=new SeedMap('map',base);
        map.loadLayers('layerFrame');
        selectTab('statustab');
    })
})();