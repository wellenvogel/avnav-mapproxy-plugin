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
import L from "leaflet";

export const forEach = function (array, callback) {
    for (let i = 0; i < array.length; i++) {
        callback(array[i]);
    }
};
export const forEachEl=(selector,cb)=>{
    let arr=document.querySelectorAll(selector);
    for (let i=0;i<arr.length;i++){
        cb(arr[i]);
    }
}
export const showHideOverlay=(id,show)=>{
    let ovl=id;
    if (typeof(id) === 'string'){
        ovl=document.getElementById(id);
    }
    if (!ovl) return;
    ovl.style.visibility=show?'unset':'hidden';
    return ovl;
}
export const closeOverlayFromButton=(btEvent)=>{
    let target=btEvent.target;
    while (target && target.parentElement){
        target=target.parentElement;
        if (target.classList.contains('overlayFrame')){
            showHideOverlay(target,false);
            return;
        }
    }
}
export const setCloseOverlayActions=()=>{
    forEachEl('button.closeOverlay',(bt)=>{
        bt.addEventListener('click',(ev)=>closeOverlayFromButton(ev));
    })
}
export const buttonEnable=(id,enable)=>{
    let bt=id;
    if (typeof(id) === 'string'){
        bt=document.getElementById(id);
    }
    if (! bt) return;
    if (enable){
        bt.removeAttribute('disabled');
    }
    else{
        bt.setAttribute('disabled','');
    }
}

export const safeName=(name)=>{
    if (! name) return;
    return name.replace(/[^a-zA-Z0-9_.,-]/g,'');
}

export const showSelectOverlay=(list,title,current,overlayId)=>{
    return new Promise((resolve, reject)=>{
        if (! overlayId) overlayId='selectOverlay';
        let parent=document.querySelector('#'+overlayId+' .overlayContent');
        if (title){
            setTextContent('#'+overlayId+' .overlayTitle',title);
        }
        if (! parent) reject("element "+overlayId+" not found");
        parent.innerHTML='';
        for (let i in list){
            let sel=list[i];
            if (sel === current) continue;
            let item=document.createElement('div');
            item.classList.add('select');
            item.addEventListener('click',()=>{
                resolve(sel);
                showHideOverlay(overlayId,false);
            })
            item.textContent=sel;
            parent.appendChild(item);
        }
        showHideOverlay(overlayId,true);
    })
}

export const STATECLASSES=['unknown','error','ok','running'];
export const setStateDisplay=(query,stateClass)=>{
    if (STATECLASSES.indexOf(stateClass) < 0) stateClass='unknown';
    forEachEl(query,(el)=>{
        STATECLASSES.forEach(function(state){
            if (state !== stateClass){
                el.classList.remove(state);
            }
            else{
                el.classList.add(state);
            }
        });
    });
}
export const setTextContent=(query,value)=>{

    forEachEl(query,(el)=>{
        if (value === undefined) value='';
        if (el.tagName === 'INPUT') el.value=value;
        else el.textContent=value;
    })
}

export const apiRequest=function(base,command){
    let url=base+"/api/"+command;
    return new Promise(function(resolve,reject){
        fetch(url)
            .then(function(r){
                return r.json();
            })
            .then(function(data){
                if (! data.status || data.status !== 'OK'){
                    reject("status: "+data.status);
                    return;
                }
                resolve(data);
                return;
            })
            .catch(function(error){
                reject(error);
            });
    });
}
export const showError=(error)=>{
    showToast(error,true);
}
export const getDateString=(d)=>{
    if (! d) d=new Date();
    let m=d.getMonth()+1;
    if (m <10) m="0"+m;
    else m=""+m;
    let day=d.getDate();
    if (day < 10) day="0"+day;
    else day=""+day;
    return d.getFullYear()+"-"+m+"-"+day;
}
let toastTimer=undefined;
export const showToast=(text,error)=>{
    if (toastTimer) window.clearTimeout(toastTimer);
    let timeout=5000;
    if (error) timeout=10000;
    toastTimer=window.setTimeout(()=>{
        showHideOverlay('toast');
    },timeout)
    setTextContent('#toast',text);
    forEachEl('#toast',(el)=>{
        if (error) el.classList.add('error');
        else el.classList.remove('error');
    })
    showHideOverlay('toast',true);
}

export const buildSelect=(parent,list,changeHandler)=>{
    if (!parent) return;
    if (typeof(parent) === 'string') parent=document.querySelector(parent);
    if (!parent) return;
    parent.innerHTML='';
    let select = document.createElement('select');
    select.addEventListener('change',(ev)=>changeHandler(ev));
    for (let lname in list) {
        let entry=list[lname];
        let o = document.createElement('option');
        o.setAttribute('value', entry.value);
        o.textContent = entry.label||entry.name;
        if (entry.selected) o.selected = true;
        select.appendChild(o);
    }
    parent.appendChild(select);
}
let radioCount=1;
export const buildRadio=(parent,list,changeHandler)=>{
    if (typeof(parent) === 'string') parent=document.querySelector(parent);
    if (! parent) return;
    radioCount++;
    let name="radio"+radioCount;
    parent.innerHTML='';
    let frame=document.createElement('div');
    frame.classList.add('radioFrame');
    list.forEach((le)=>{
        let el=document.createElement('span');
        el.classList.add('label');
        el.textContent=le.label;
        frame.appendChild(el);
        el=document.createElement('input');
        el.setAttribute('type','radio');
        el.setAttribute('name',name);
        el.setAttribute('value',le.value);
        if (le.checked) el.checked=true;
        el.addEventListener('change',(ev)=>{
            changeHandler(ev.target.getAttribute('value'));
        })
        frame.appendChild(el);
    });
    parent.appendChild(frame);
    return frame;
}
export const changeRadio=(parent,value)=>{
    if (typeof(parent) === 'string') parent=document.querySelector(parent);
    if (!parent) return;
    forEach(parent.querySelectorAll('input[type="radio"]'),(el)=>{
        if (el.getAttribute('value') === value) el.checked=true;
        else el.checked=false;
    })
}

