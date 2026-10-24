/* The chess board's pointer-capture approach, adapted for rack and draft tiles. */
(() => {
    let gesture = null;
    let busy = false;
    let queued = null;
    let sequence = 0;
    let suppressed = null;
    const actionable = el => el instanceof Element ? el.closest('[data-action]') : null;
    const isBusy = () => busy || document.querySelector('#game-view[data-busy="true"]');
    function send(action) {
        if (!window.dash_clientside?.set_props) return;
        if (isBusy()) { queued = action; return; }
        busy = true;
        const blank = document.querySelector('#blank-letter')?.value || 'A';
        window.dash_clientside.set_props('action',{data:{...action,blank,nonce:Date.now()+ ++sequence}});
    }
    function clear() {
        if (gesture?.scrollFrame) cancelAnimationFrame(gesture.scrollFrame);
        gesture?.ghost?.remove();
        gesture?.source.classList.remove('drag-source');
        document.querySelectorAll('.drag-over').forEach(el => el.classList.remove('drag-over'));
        gesture = null;
    }
    function edgeScroll() {
        if (!gesture?.dragging || gesture.cancelled) return;
        const y=gesture.pointerY;
        const delta=y<45 ? -10 : y>innerHeight-45 ? 10 : 0;
        if (delta) window.scrollBy(0,delta);
        gesture.scrollFrame=requestAnimationFrame(edgeScroll);
    }
    function clickAction(element) {
        if (!element || element.disabled) return;
        const action = {type:element.dataset.action};
        if (element.dataset.cell !== undefined) action.cell = Number(element.dataset.cell);
        if (element.dataset.slot !== undefined) action.slot = Number(element.dataset.slot);
        send(action);
    }
    document.addEventListener('pointerdown',event => {
        const source = actionable(event.target);
        if (!source || source.dataset.draggable!=='true' || isBusy() || gesture || event.button!==0 || !event.isPrimary) return;
        gesture = {source,id:event.pointerId,x:event.clientX,y:event.clientY,dragging:false};
        source.setPointerCapture(event.pointerId);
    });
    document.addEventListener('pointermove',event => {
        if (!gesture || gesture.id!==event.pointerId || gesture.cancelled) return;
        if (!gesture.dragging && Math.hypot(event.clientX-gesture.x,event.clientY-gesture.y)>6) {
            gesture.dragging = true;
            gesture.source.classList.add('drag-source');
            gesture.ghost = gesture.source.querySelector('.letter-tile').cloneNode(true);
            gesture.ghost.classList.add('drag-ghost');
            gesture.ghost.style.width = `${gesture.source.getBoundingClientRect().width}px`;
            document.body.appendChild(gesture.ghost);
            gesture.pointerY=event.clientY;
            gesture.scrollFrame=requestAnimationFrame(edgeScroll);
        }
        if (!gesture.dragging) return;
        event.preventDefault();
        gesture.pointerY=event.clientY;
        gesture.ghost.style.left = `${event.clientX}px`;
        gesture.ghost.style.top = `${event.clientY}px`;
        document.querySelector('.drag-over')?.classList.remove('drag-over');
        document.elementFromPoint(event.clientX,event.clientY)?.closest('.board-cell:not(.committed),.rack')?.classList.add('drag-over');
    },{passive:false});
    document.addEventListener('pointerup',event => {
        if (!gesture || gesture.id!==event.pointerId) return;
        const {source,dragging,cancelled} = gesture;
        if (source.hasPointerCapture(event.pointerId)) source.releasePointerCapture(event.pointerId);
        suppressed = source;
        if (!cancelled) {
            if (dragging) {
                const target = document.elementFromPoint(event.clientX,event.clientY);
                const cell = target?.closest('[data-cell]');
                if (cell && cell!==source) send({type:'drop',cell:Number(cell.dataset.cell),source:source.dataset.source});
                else if (target?.closest('[data-rack-target]') && source.dataset.source.startsWith('cell:'))
                    send({type:'return',cell:Number(source.dataset.cell)});
            } else clickAction(source);
        }
        clear();
    });
    document.addEventListener('click',event => {
        const target = actionable(event.target);
        if (!target) return;
        if (event.detail!==0 && target===suppressed) { suppressed=null; return; }
        suppressed=null;
        clickAction(target);
    });
    document.addEventListener('keydown',event => {
        if (event.key==='Escape' && gesture) {
            gesture.cancelled=true;
            gesture.ghost?.remove();
            gesture.source.classList.remove('drag-source');
        }
        const cell = event.target.closest?.('.board-cell');
        if (!cell || !['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(event.key)) return;
        event.preventDefault();
        const index = Number(cell.dataset.cell);
        const offset = {ArrowLeft:-1,ArrowRight:1,ArrowUp:-15,ArrowDown:15}[event.key];
        if ((event.key==='ArrowLeft' && index%15===0) || (event.key==='ArrowRight' && index%15===14)) return;
        document.getElementById(`cell-${index+offset}`)?.focus();
    });
    document.addEventListener('pointercancel',clear);
    window.addEventListener('blur',clear);
    new MutationObserver(records => {
        if (records.some(r => r.target.id==='game-view' && r.target.dataset.busy==='false')) {
            busy=false;
            if (queued) { const action=queued; queued=null; send(action); }
        }
    }).observe(document.documentElement,{attributes:true,attributeFilter:['data-busy'],subtree:true});
})();
