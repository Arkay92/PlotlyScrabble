/* Pointer capture, keyboard controls and live multiplayer WebSocket bridge for Scrabble. */
(() => {
    let gesture = null;
    let suppressClickUntil = 0;
    let suppressedTarget = null;
    let busy = false;
    let busyTimer = null;
    let queuedAction = null;
    let sequence = 0;
    let socket = null;
    let socketCode = null;
    let reconnectTimer = null;
    let wsSupported = true;
    let suppressSocketUntil = 0;

    const actionable = el => el instanceof Element ? el.closest('[data-action]') : null;
    const isBusy = () => busy || document.querySelector('#game-view[data-busy="true"]');

    function clearBusy() {
        busy = false;
        if (busyTimer) {
            clearTimeout(busyTimer);
            busyTimer = null;
        }
        document.querySelectorAll('.move-ghost, .drag-ghost').forEach(el => el.remove());
        document.querySelectorAll('.drag-source').forEach(el => el.classList.remove('drag-source'));
        document.querySelectorAll('.drag-over').forEach(el => el.classList.remove('drag-over'));
        if (queuedAction) {
            const next = queuedAction;
            queuedAction = null;
            send(next);
        }
    }

    function send(action) {
        if (!window.dash_clientside?.set_props || !action) return;
        const isGameAction = action.type === 'cell' || action.type === 'rack' || action.type === 'drop' || action.type === 'return' || action.type === 'play' || action.type === 'mp-sync';
        if (isGameAction && isBusy()) {
            if (action.type !== 'mp-sync') queuedAction = action;
            return;
        }
        if (!isGameAction) {
            queuedAction = null;
        }
        busy = true;
        if (busyTimer) clearTimeout(busyTimer);
        busyTimer = setTimeout(clearBusy, 4000);

        const blank = document.querySelector('#blank-letter')?.value || 'A';
        window.dash_clientside.set_props('action', {data: {...action, blank, nonce: Date.now() + ++sequence}});
    }

    function animateTileMove(fromEl, toEl) {
        if (!fromEl || !toEl || fromEl === toEl) return;
        const tile = fromEl.querySelector('.letter-tile');
        if (!tile) return;

        document.querySelectorAll('.move-ghost, .drag-ghost').forEach(el => el.remove());

        const rFrom = fromEl.getBoundingClientRect();
        const rTo = toEl.getBoundingClientRect();

        const ghost = tile.cloneNode(true);
        ghost.className = 'move-ghost';
        ghost.style.width = `${rFrom.width}px`;
        ghost.style.left = `${rFrom.left + rFrom.width / 2}px`;
        ghost.style.top = `${rFrom.top + rFrom.height / 2}px`;
        document.body.appendChild(ghost);

        fromEl.classList.add('drag-source');

        requestAnimationFrame(() => {
            ghost.style.transition = 'left 0.14s cubic-bezier(0.2, 0, 0.2, 1), top 0.14s cubic-bezier(0.2, 0, 0.2, 1)';
            ghost.style.left = `${rTo.left + rTo.width / 2}px`;
            ghost.style.top = `${rTo.top + rTo.height / 2}px`;
        });
        // Pinned until MutationObserver receives new board DOM and calls clearBusy()
    }

    function clearGesture() {
        if (gesture?.scrollFrame) cancelAnimationFrame(gesture.scrollFrame);
        if (gesture?.ghost) gesture.ghost.remove();
        if (gesture?.source) gesture.source.classList.remove('drag-source');
        document.querySelectorAll('.drag-over').forEach(el => el.classList.remove('drag-over'));
        gesture = null;
    }

    function edgeScroll() {
        if (!gesture?.dragging || gesture.cancelled) return;
        const y = gesture.pointerY;
        const delta = y < 45 ? -10 : y > window.innerHeight - 45 ? 10 : 0;
        if (delta) window.scrollBy(0, delta);
        gesture.scrollFrame = requestAnimationFrame(edgeScroll);
    }

    function applySyncEvent(msg, code) {
        if (performance.now() < suppressSocketUntil) return;
        if (!msg || msg.type !== 'sync' || msg.code !== code) return;
        const activeSession = document.querySelector('.mp-session');
        if (!activeSession || activeSession.offsetParent === null || activeSession.dataset.roomCode !== code) return;
        const currentVersion = Number(activeSession.dataset.mpVersion || 0);
        const currentConnected = activeSession.dataset.mpConnected === 'true';
        if (Number(msg.version) > currentVersion || Boolean(msg.connected) !== currentConnected) {
            send({type: 'mp-sync', version: msg.version});
        }
    }

    function closeSocket() {
        if (reconnectTimer) {
            clearTimeout(reconnectTimer);
            reconnectTimer = null;
        }
        if (socket) {
            const current = socket;
            socket = null;
            socketCode = null;
            current.onclose = null;
            current.onmessage = null;
            try { current.close(); } catch (_) {}
        }
    }

    function syncMultiplayerSocket() {
        if (performance.now() < suppressSocketUntil) {
            closeSocket();
            return;
        }
        const session = document.querySelector('.mp-session');
        const roomVisible = Boolean(session && session.offsetParent !== null);
        const code = roomVisible ? (session.dataset.roomCode || null) : null;
        if (code) {
            const expectedSearch = `?code=${encodeURIComponent(code)}`;
            if (window.location.search !== expectedSearch && window.history?.replaceState) {
                window.history.replaceState(null, '', `${window.location.pathname}${expectedSearch}`);
            }
        }
        if (!wsSupported) return;
        if (!code) {
            closeSocket();
            return;
        }
        if (socket && socketCode === code && socket.readyState <= WebSocket.OPEN) {
            return;
        }
        closeSocket();
        socketCode = code;
        let receivedFrame = false;
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws?code=${encodeURIComponent(code)}`;
        try {
            socket = new WebSocket(wsUrl);
        } catch (_) {
            socket = null;
            wsSupported = false;
        }
        if (socket) {
            socket.onmessage = (event) => {
                receivedFrame = true;
                try {
                    applySyncEvent(JSON.parse(event.data), code);
                } catch (_) {}
            };
            socket.onclose = () => {
                socket = null;
                if (!receivedFrame) {
                    wsSupported = false;
                    return;
                }
                if (document.querySelector('.mp-session')?.dataset.roomCode === code) {
                    reconnectTimer = setTimeout(syncMultiplayerSocket, 2000);
                }
            };
        }
    }

    // Pointer Events
    document.addEventListener('pointerdown', event => {
        const source = actionable(event.target);
        if (!source || source.dataset.draggable !== 'true' || isBusy() || gesture || event.button !== 0 || !event.isPrimary) return;
        const rect = source.getBoundingClientRect();
        gesture = {
            source,
            id: event.pointerId,
            startX: event.clientX,
            startY: event.clientY,
            offsetX: event.clientX - (rect.left + rect.width / 2),
            offsetY: event.clientY - (rect.top + rect.height / 2),
            dragging: false
        };
        try {
            source.setPointerCapture(event.pointerId);
        } catch (_) {}
    });

    document.addEventListener('pointermove', event => {
        if (!gesture || gesture.id !== event.pointerId || gesture.cancelled) return;
        const dist = Math.hypot(event.clientX - gesture.startX, event.clientY - gesture.startY);
        if (!gesture.dragging && dist > 6) {
            gesture.dragging = true;
            gesture.source.classList.add('drag-source');
            const tile = gesture.source.querySelector('.letter-tile');
            if (tile) {
                const ghost = tile.cloneNode(true);
                const rect = gesture.source.getBoundingClientRect();
                ghost.className = 'drag-ghost';
                ghost.style.width = `${rect.width}px`;
                ghost.style.left = `${event.clientX - gesture.offsetX}px`;
                ghost.style.top = `${event.clientY - gesture.offsetY}px`;
                document.body.appendChild(ghost);
                gesture.ghost = ghost;
            }
            gesture.pointerY = event.clientY;
            gesture.scrollFrame = requestAnimationFrame(edgeScroll);
        }
        if (!gesture.dragging || !gesture.ghost) return;
        event.preventDefault();
        gesture.pointerY = event.clientY;
        gesture.ghost.style.left = `${event.clientX - gesture.offsetX}px`;
        gesture.ghost.style.top = `${event.clientY - gesture.offsetY}px`;

        document.querySelector('.drag-over')?.classList.remove('drag-over');
        const target = document.elementFromPoint(event.clientX, event.clientY);
        target?.closest('.board-cell:not(.committed), [data-rack-target]')?.classList.add('drag-over');
    }, {passive: false});

    document.addEventListener('pointerup', event => {
        if (!gesture || gesture.id !== event.pointerId) return;
        const {source, dragging, startX, startY, ghost} = gesture;
        try {
            if (source.hasPointerCapture(event.pointerId)) source.releasePointerCapture(event.pointerId);
        } catch (_) {}

        if (gesture.cancelled) {
            suppressClickUntil = performance.now() + 400;
            suppressedTarget = source;
            clearGesture();
            return;
        }

        if (dragging) {
            const targetEl = document.elementFromPoint(event.clientX, event.clientY);
            const cell = targetEl?.closest('[data-cell]');
            const rackTarget = targetEl?.closest('[data-rack-target]');
            suppressClickUntil = performance.now() + 400;
            suppressedTarget = source;

            if (cell && cell !== source && !cell.classList.contains('committed')) {
                if (ghost) {
                    const rTo = cell.getBoundingClientRect();
                    gesture.ghost = null;
                    ghost.className = 'move-ghost';
                    requestAnimationFrame(() => {
                        ghost.style.transition = 'left 0.12s cubic-bezier(0.2, 0, 0.2, 1), top 0.12s cubic-bezier(0.2, 0, 0.2, 1)';
                        ghost.style.left = `${rTo.left + rTo.width / 2}px`;
                        ghost.style.top = `${rTo.top + rTo.height / 2}px`;
                    });
                }
                clearGesture();
                send({type: 'drop', cell: Number(cell.dataset.cell), source: source.dataset.source});
            } else if (rackTarget && source.dataset.source?.startsWith('cell:')) {
                if (ghost) {
                    gesture.ghost = null;
                    ghost.remove();
                }
                clearGesture();
                send({type: 'return', cell: Number(source.dataset.cell)});
            } else {
                if (ghost) {
                    const rFrom = source.getBoundingClientRect();
                    gesture.ghost = null;
                    ghost.className = 'move-ghost';
                    requestAnimationFrame(() => {
                        ghost.style.transition = 'left 0.14s cubic-bezier(0.2, 0, 0.2, 1), top 0.14s cubic-bezier(0.2, 0, 0.2, 1)';
                        ghost.style.left = `${rFrom.left + rFrom.width / 2}px`;
                        ghost.style.top = `${rFrom.top + rFrom.height / 2}px`;
                    });
                    setTimeout(() => {
                        ghost.remove();
                        source.classList.remove('drag-source');
                    }, 160);
                }
                clearGesture();
            }
        } else {
            const dist = Math.hypot(event.clientX - startX, event.clientY - startY);
            clearGesture();
            if (dist < 12) {
                suppressClickUntil = performance.now() + 400;
                suppressedTarget = source;

                // Check tap-to-place: selected rack slot -> empty board cell
                const selectedRackSlot = document.querySelector('.rack-slot.selected');
                if (selectedRackSlot && source.classList.contains('board-cell') && !source.classList.contains('committed') && !source.classList.contains('draft')) {
                    animateTileMove(selectedRackSlot, source);
                    send({type: 'drop', cell: Number(source.dataset.cell), source: selectedRackSlot.dataset.source});
                    return;
                }

                const action = {type: source.dataset.action};
                if (source.dataset.cell !== undefined) action.cell = Number(source.dataset.cell);
                if (source.dataset.slot !== undefined) action.slot = Number(source.dataset.slot);
                send(action);
            }
        }
    });

    document.addEventListener('pointercancel', clearGesture);

    // Click handler for UI buttons
    document.addEventListener('click', event => {
        const target = event.target instanceof Element ? event.target : null;
        if (!target) return;

        // Friends Widget Toggle
        const friendsToggle = target.closest('#friends-toggle-btn, #friends-close-btn');
        if (friendsToggle) {
            document.getElementById('friends-widget')?.classList.toggle('friends-open');
            return;
        }

        // Profile View Button
        const profileBtn = target.closest('[data-view-profile]');
        if (profileBtn) {
            const user = profileBtn.dataset.viewProfile || '';
            if (user) send({type: 'view-profile', username: user});
            return;
        }

        // Add/Remove Friend
        const toggleFriendBtn = target.closest('[data-toggle-friend]');
        if (toggleFriendBtn) {
            const user = toggleFriendBtn.dataset.toggleFriend || '';
            if (user) send({type: 'toggle-friend', username: user});
            return;
        }

        // Mobile Burger Menu
        const burgerBtn = target.closest('#burger-menu-btn');
        const siteNav = document.getElementById('site-nav');
        if (burgerBtn) {
            const isOpen = siteNav?.classList.toggle('nav-open');
            burgerBtn.setAttribute('aria-expanded', String(Boolean(isOpen)));
            return;
        }
        if (siteNav?.classList.contains('nav-open')) {
            if (!siteNav.contains(target) || target.closest('#site-nav button, #site-nav a')) {
                siteNav.classList.remove('nav-open');
                document.getElementById('burger-menu-btn')?.setAttribute('aria-expanded', 'false');
            }
        }

        // User Dropdown Menu
        const userMenu = document.getElementById('user-menu');
        if (userMenu?.hasAttribute('open') && (!userMenu.contains(target) || target.closest('.user-dropdown-menu button'))) {
            setTimeout(() => userMenu.removeAttribute('open'), 50);
        }

        // Navigation screens & Leave room
        const screenNavBtn = target.closest('#brand-home-btn, #nav-play-btn, #mp-leave-btn, #nav-profile-btn, #nav-leaderboard-btn, #mp-tab-lobby-btn, #mp-tab-find-btn, #mp-choose-join-btn, #nav-about-btn, #footer-about-btn, #menu-about-btn, #about-back-btn, #leaderboard-back-btn, #profile-back-btn');
        if (screenNavBtn) {
            queuedAction = null;
            suppressSocketUntil = performance.now() + 1500;
            document.querySelector('.mp-session')?.removeAttribute('data-room-code');
            closeSocket();
            if (window.location.search && window.history?.replaceState) {
                window.history.replaceState(null, '', window.location.pathname);
            }
            return;
        }

        // Resume saved game
        const resumeBtn = target.closest('[data-resume-game]');
        if (resumeBtn) {
            const gid = resumeBtn.dataset.resumeGame || '';
            if (gid.startsWith('mp:')) {
                suppressSocketUntil = 0;
                const code = gid.slice(3);
                if (code && window.history?.replaceState) {
                    window.history.replaceState(null, '', `${window.location.pathname}?code=${encodeURIComponent(code)}`);
                }
            }
            send({type: 'resume-game', game_id: gid});
            return;
        }

        // Dismiss saved game
        const dismissBtn = target.closest('[data-dismiss-game]');
        if (dismissBtn) {
            send({type: 'dismiss-game', game_id: dismissBtn.dataset.dismissGame});
            return;
        }

        // Join open multiplayer game
        const joinOpenBtn = target.closest('[data-join-open-game]');
        if (joinOpenBtn) {
            const code = joinOpenBtn.dataset.joinOpenGame || '';
            suppressSocketUntil = 0;
            if (code && window.history?.replaceState) {
                window.history.replaceState(null, '', `${window.location.pathname}?code=${encodeURIComponent(code)}`);
            }
            send({type: 'mp-join', code});
            return;
        }

        // Copy room code
        const copyBtn = target.closest('#mp-copy-btn');
        if (copyBtn) {
            const code = copyBtn.dataset.code || '';
            if (code && navigator.clipboard?.writeText) {
                navigator.clipboard.writeText(code).catch(() => {});
            }
            copyBtn.textContent = 'Copied!';
            setTimeout(() => { copyBtn.textContent = 'Copy code'; }, 1400);
            return;
        }

        // Copy shareable room link
        const linkBtn = target.closest('#mp-copy-link-btn');
        if (linkBtn) {
            const code = linkBtn.dataset.code || '';
            const link = `${window.location.origin}${window.location.pathname}?code=${encodeURIComponent(code)}`;
            if (code && navigator.clipboard?.writeText) {
                navigator.clipboard.writeText(link).catch(() => {});
            }
            linkBtn.textContent = 'Link copied!';
            setTimeout(() => { linkBtn.textContent = 'Copy link'; }, 1400);
            return;
        }

        // Normal Actionable Button Click
        const actionEl = actionable(target);
        if (!actionEl) return;
        if (event.detail !== 0 && performance.now() < suppressClickUntil && actionEl === suppressedTarget) {
            suppressClickUntil = 0;
            return;
        }

        const action = {type: actionEl.dataset.action};
        if (actionEl.dataset.cell !== undefined) action.cell = Number(actionEl.dataset.cell);
        if (actionEl.dataset.slot !== undefined) action.slot = Number(actionEl.dataset.slot);
        send(action);
    });

    document.addEventListener('keydown', event => {
        if (event.key === 'Escape') {
            const siteNav = document.getElementById('site-nav');
            if (siteNav?.classList.contains('nav-open')) {
                siteNav.classList.remove('nav-open');
                document.getElementById('burger-menu-btn')?.setAttribute('aria-expanded', 'false');
            }
            if (gesture) {
                gesture.cancelled = true;
                gesture.ghost?.remove();
                gesture.source.classList.remove('drag-source');
                document.querySelectorAll('.drag-over').forEach(el => el.classList.remove('drag-over'));
            }
        }
        const cell = event.target.closest?.('.board-cell');
        if (!cell || !['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(event.key)) return;
        event.preventDefault();
        const index = Number(cell.dataset.cell);
        const offset = {ArrowLeft: -1, ArrowRight: 1, ArrowUp: -15, ArrowDown: 15}[event.key];
        if ((event.key === 'ArrowLeft' && index % 15 === 0) || (event.key === 'ArrowRight' && index % 15 === 14)) return;
        document.getElementById(`cell-${index + offset}`)?.focus();
    });

    window.addEventListener('blur', clearGesture);

    // MutationObserver to clear busy status and ghosts when DOM updates
    const observer = new MutationObserver((records) => {
        let domChanged = false;
        for (const record of records) {
            const t = record.target;
            if (t && (t.id === 'game-view' || t.classList?.contains('board-frame') || t.closest?.('#game-view'))) {
                domChanged = true;
                break;
            }
        }
        if (domChanged) {
            clearBusy();
        }
        syncMultiplayerSocket();
    });
    observer.observe(document.documentElement, {
        attributes: true,
        childList: true,
        attributeFilter: ['data-busy', 'data-room-code', 'data-mp-version'],
        subtree: true
    });
})();
