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
export const forEach = function (array, callback, scope) {
    for (let i = 0; i < array.length; i++) {
        callback.call(scope, i, array[i]); // passes back stuff we need
    }
};
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
    forEach(document.querySelectorAll('button.closeOverlay'),(i,bt)=>{
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


