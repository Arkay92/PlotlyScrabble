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
    const isBusy = () => busy || document.querySelector('#game-view[data-busy="true"], #game-view-container[data-busy="true"]');

    function clearBusy() {
        busy = false;
        if (busyTimer) {
            clearTimeout(busyTimer);
            busyTimer = null;
        }
        document.getElementById('game-view')?.removeAttribute('data-busy');
        document.getElementById('game-view-container')?.removeAttribute('data-busy');
        document.querySelectorAll('.move-ghost').forEach(el => el.remove());
        if (!gesture?.dragging) {
            document.querySelectorAll('.drag-ghost').forEach(el => el.remove());
            document.querySelectorAll('.drag-source').forEach(el => el.classList.remove('drag-source'));
            document.querySelectorAll('.drag-over').forEach(el => el.classList.remove('drag-over'));
        }
        if (queuedAction) {
            const next = queuedAction;
            queuedAction = null;
            send(next);
        }
    }

    function send(action) {
        if (!window.dash_clientside?.set_props || !action) return;
        const requiresServerLock = action.type === 'play' || action.type === 'pass' || action.type === 'exchange-confirm';
        if (requiresServerLock && isBusy()) {
            queuedAction = action;
            return;
        }
        if (!requiresServerLock) {
            queuedAction = null;
        }
        if (requiresServerLock) {
            busy = true;
            if (busyTimer) clearTimeout(busyTimer);
            busyTimer = setTimeout(clearBusy, 800);

            document.getElementById('game-view')?.setAttribute('data-busy', 'true');
            document.getElementById('game-view-container')?.setAttribute('data-busy', 'true');
        }

        const blank = document.querySelector('#blank-letter')?.value || 'A';
        window.dash_clientside.set_props('action', {data: {...action, blank, nonce: Date.now() + ++sequence}});
    }

    function shuffleRackAnimation() {
        const rackEl = document.querySelector('.rack');
        if (!rackEl) return;
        const slots = Array.from(rackEl.querySelectorAll('.rack-slot:not(.used)'));
        if (slots.length <= 1) return;

        const tileContents = slots.map(slot => ({
            html: slot.innerHTML,
            ariaLabel: slot.getAttribute('aria-label')
        }));

        for (let i = tileContents.length - 1; i > 0; i--) {
            const j = Math.floor(Math.random() * (i + 1));
            const tmp = tileContents[i];
            tileContents[i] = tileContents[j];
            tileContents[j] = tmp;
        }

        slots.forEach((slot, idx) => {
            slot.style.transition = 'transform 0.10s cubic-bezier(0.2, 0, 0.2, 1), opacity 0.10s ease';
            slot.style.transform = 'scale(0.85) translateY(-4px)';
            slot.style.opacity = '0.65';
            setTimeout(() => {
                slot.innerHTML = tileContents[idx].html;
                if (tileContents[idx].ariaLabel) slot.setAttribute('aria-label', tileContents[idx].ariaLabel);
                slot.style.transform = 'scale(1.06) translateY(0)';
                slot.style.opacity = '1';
                setTimeout(() => {
                    slot.style.transform = '';
                    slot.style.transition = '';
                }, 110);
            }, 60);
        });
    }

    function animateTileMove(fromEl, toEl) {
        if (!fromEl || !toEl || fromEl === toEl) return;
        const tile = fromEl.querySelector('.letter-tile');
        if (!tile) return;

        document.querySelectorAll('.move-ghost, .drag-ghost').forEach(el => el.remove());

        const rFrom = fromEl.getBoundingClientRect();

        // Resolve destination element: if moving to rack, target the specific rack slot!
        let destEl = toEl;
        const isToRack = destEl.classList.contains('rack') || destEl.classList.contains('rack-panel') || destEl.hasAttribute('data-rack-target');
        if (isToRack) {
            const slotIdx = fromEl.dataset.rackSlot;
            destEl = (slotIdx !== undefined && slotIdx !== '' && document.getElementById(`rack-${slotIdx}`)) ||
                     document.querySelector('.rack-slot.used') ||
                     document.querySelector('.rack-slot') ||
                     destEl;
        }

        const rTo = destEl.getBoundingClientRect();
        // Sizing: never exceed standard tile size (~52px) to prevent stretching across rack
        const targetW = Math.min(rTo.width, 52);
        const targetH = Math.min(rTo.height, 52);

        const ghost = tile.cloneNode(true);
        ghost.className = tile.className + ' move-ghost';
        ghost.style.width = `${rFrom.width}px`;
        ghost.style.height = `${rFrom.height}px`;
        ghost.style.fontSize = window.getComputedStyle(tile).fontSize;
        ghost.style.left = `${rFrom.left + rFrom.width / 2}px`;
        ghost.style.top = `${rFrom.top + rFrom.height / 2}px`;
        document.body.appendChild(ghost);

        fromEl.classList.add('drag-source');

        if (fromEl.classList.contains('board-cell')) {
            // Eager Recall: board cell -> rack slot
            fromEl.classList.remove('draft');
            const prem = fromEl.dataset.premium || '';
            fromEl.innerHTML = `<span class="premium-label">${prem}</span>`;
            delete fromEl.dataset.source;
            fromEl.dataset.draggable = 'false';
            if (destEl.classList.contains('rack-slot') && !destEl.querySelector('.letter-tile')) {
                destEl.innerHTML = '';
                destEl.appendChild(tile.cloneNode(true));
            }
        } else {
            // Eager Placement: rack slot -> board cell
            fromEl.classList.add('used');
            toEl.classList.add('draft');
            toEl.dataset.source = `cell:${toEl.dataset.cell}`;
            toEl.dataset.rackSlot = fromEl.dataset.slot || '';
            toEl.dataset.draggable = 'true';
        }

        requestAnimationFrame(() => {
            ghost.style.transition = 'left 0.11s cubic-bezier(0.2, 0, 0.2, 1), top 0.11s cubic-bezier(0.2, 0, 0.2, 1), width 0.11s ease, height 0.11s ease, opacity 0.11s ease';
            ghost.style.left = `${rTo.left + rTo.width / 2}px`;
            ghost.style.top = `${rTo.top + rTo.height / 2}px`;
            ghost.style.width = `${targetW}px`;
            ghost.style.height = `${targetH}px`;
            if (fromEl.classList.contains('board-cell')) ghost.style.opacity = '0.85';
        });

        setTimeout(() => {
            if (!fromEl.classList.contains('board-cell')) {
                toEl.innerHTML = '';
                toEl.appendChild(tile.cloneNode(true));
            } else if (destEl.classList.contains('rack-slot')) {
                if (!destEl.querySelector('.letter-tile')) {
                    destEl.innerHTML = '';
                    destEl.appendChild(tile.cloneNode(true));
                }
                destEl.classList.remove('used');
                destEl.dataset.draggable = 'true';
            }
            ghost.remove();
            fromEl.classList.remove('drag-source');
        }, 110);
    }

    function clearGesture() {
        if (gesture?.scrollFrame) cancelAnimationFrame(gesture.scrollFrame);
        if (gesture?.ghost) gesture.ghost.remove();
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
        const hasSelectedRack = Boolean(document.querySelector('.rack-slot.selected'));
        const isPlaceTarget = hasSelectedRack && source?.classList?.contains('board-cell') && !source?.classList?.contains('committed') && !source?.classList?.contains('draft');
        const isDraggable = source && (source.dataset.draggable === 'true' || source.classList.contains('draft') || isPlaceTarget);
        if (!source || !isDraggable || isBusy() || gesture || (event.button && event.button !== 0)) return;
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
                ghost.className = tile.className + ' drag-ghost';
                ghost.style.width = `${rect.width}px`;
                ghost.style.height = `${rect.height}px`;
                ghost.style.fontSize = window.getComputedStyle(tile).fontSize;
                ghost.style.left = `${event.clientX - gesture.offsetX}px`;
                ghost.style.top = `${event.clientY - gesture.offsetY}px`;
                document.body.appendChild(ghost);
                gesture.ghost = ghost;
                gesture.tileClass = tile.className;
            }
            gesture.pointerY = event.clientY;
            gesture.scrollFrame = requestAnimationFrame(edgeScroll);
        }
        if (!gesture.dragging || !gesture.ghost) return;
        event.preventDefault();
        gesture.pointerY = event.clientY;
        gesture.ghost.style.left = `${event.clientX - gesture.offsetX}px`;
        gesture.ghost.style.top = `${event.clientY - gesture.offsetY}px`;

        document.querySelectorAll('.drag-over').forEach(el => el.classList.remove('drag-over'));
        const target = document.elementFromPoint(event.clientX, event.clientY);
        const cell = target?.closest('.board-cell');
        const rackTarget = target?.closest('[data-rack-target], .rack, .rack-panel, .rack-slot');
        if (cell && !cell.classList.contains('committed') && !cell.classList.contains('draft') && cell !== gesture.source) {
            cell.classList.add('drag-over');
        } else if (rackTarget && (gesture.source?.dataset?.source?.startsWith('cell:') || gesture.source?.classList?.contains('draft'))) {
            rackTarget.classList.add('drag-over');
        }
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
            if (ghost) ghost.remove();
            source.classList.remove('drag-source');
            clearGesture();
            return;
        }

        if (dragging) {
            const targetEl = document.elementFromPoint(event.clientX, event.clientY);
            const cell = targetEl?.closest('[data-cell]');
            const rackTarget = targetEl?.closest('[data-rack-target], .rack, .rack-panel, .rack-slot');
            suppressClickUntil = performance.now() + 400;
            suppressedTarget = source;

            const isTargetEmptyCell = cell && !cell.classList.contains('committed') && !cell.classList.contains('draft') && cell !== source;

            if (isTargetEmptyCell) {
                const rTo = cell.getBoundingClientRect();
                const tileEl = source.querySelector('.letter-tile');
                if (ghost) {
                    gesture.ghost = null;
                    ghost.className = (gesture.tileClass || 'letter-tile') + ' move-ghost';
                    requestAnimationFrame(() => {
                        ghost.style.transition = 'left 0.10s cubic-bezier(0.2, 0, 0.2, 1), top 0.10s cubic-bezier(0.2, 0, 0.2, 1), width 0.10s ease, height 0.10s ease';
                        ghost.style.left = `${rTo.left + rTo.width / 2}px`;
                        ghost.style.top = `${rTo.top + rTo.height / 2}px`;
                        ghost.style.width = `${rTo.width * 0.96}px`;
                        ghost.style.height = `${rTo.height * 0.95}px`;
                    });
                    setTimeout(() => {
                        if (tileEl) {
                            cell.innerHTML = '';
                            cell.appendChild(tileEl.cloneNode(true));
                        }
                        ghost.remove();
                    }, 110);
                } else if (tileEl) {
                    cell.innerHTML = '';
                    cell.appendChild(tileEl.cloneNode(true));
                }
                // Eagerly place: mark source as used and cell as draft immediately like chess
                source.classList.add('used');
                cell.classList.add('draft');
                cell.dataset.source = `cell:${cell.dataset.cell}`;
                cell.dataset.rackSlot = source.dataset.slot || '';
                cell.dataset.draggable = 'true';
                clearGesture();
                send({type: 'drop', cell: Number(cell.dataset.cell), source: source.dataset.source});
            } else if (rackTarget && (source.dataset.source?.startsWith('cell:') || source.classList.contains('draft') || source.dataset.cell !== undefined)) {
                // Dragged draft tile back to rack: animate return and recall tile
                const slotIdx = source.dataset.rackSlot;
                const destSlot = (slotIdx !== undefined && slotIdx !== '' && document.getElementById(`rack-${slotIdx}`)) ||
                                 (targetEl?.closest('.rack-slot')) ||
                                 document.querySelector('.rack-slot.used') ||
                                 document.querySelector('.rack-slot') ||
                                 rackTarget;
                const rRack = destSlot.getBoundingClientRect();
                const targetW = Math.min(rRack.width, 52);
                const targetH = Math.min(rRack.height, 52);

                if (ghost) {
                    gesture.ghost = null;
                    ghost.className = (gesture.tileClass || 'letter-tile') + ' move-ghost';
                    requestAnimationFrame(() => {
                        ghost.style.transition = 'left 0.11s cubic-bezier(0.2, 0, 0.2, 1), top 0.11s cubic-bezier(0.2, 0, 0.2, 1), width 0.11s ease, height 0.11s ease, opacity 0.11s ease';
                        ghost.style.left = `${rRack.left + rRack.width / 2}px`;
                        ghost.style.top = `${rRack.top + rRack.height / 2}px`;
                        ghost.style.width = `${targetW}px`;
                        ghost.style.height = `${targetH}px`;
                        ghost.style.opacity = '0.85';
                    });
                    setTimeout(() => {
                        ghost.remove();
                        if (destSlot.classList.contains('rack-slot')) {
                            if (!destSlot.querySelector('.letter-tile')) {
                                const tileEl = source.querySelector('.letter-tile');
                                if (tileEl) {
                                    destSlot.innerHTML = '';
                                    destSlot.appendChild(tileEl.cloneNode(true));
                                }
                            }
                            destSlot.classList.remove('used');
                            destSlot.dataset.draggable = 'true';
                        }
                    }, 110);
                } else if (destSlot.classList.contains('rack-slot')) {
                    if (!destSlot.querySelector('.letter-tile')) {
                        const tileEl = source.querySelector('.letter-tile');
                        if (tileEl) {
                            destSlot.innerHTML = '';
                            destSlot.appendChild(tileEl.cloneNode(true));
                        }
                    }
                    destSlot.classList.remove('used');
                    destSlot.dataset.draggable = 'true';
                }
                source.classList.remove('draft');
                const prem = source.dataset.premium || '';
                source.innerHTML = `<span class="premium-label">${prem}</span>`;
                delete source.dataset.source;
                source.dataset.draggable = 'false';
                clearGesture();
                send({type: 'return', cell: Number(source.dataset.cell)});
            } else {
                // Illegal drop (e.g. dropped on committed/draft cell, or outside board): snap back to source
                if (ghost) {
                    const rFrom = source.getBoundingClientRect();
                    gesture.ghost = null;
                    ghost.className = (gesture.tileClass || 'letter-tile') + ' move-ghost';
                    requestAnimationFrame(() => {
                        ghost.style.transition = 'left 0.14s cubic-bezier(0.2, 0, 0.2, 1), top 0.14s cubic-bezier(0.2, 0, 0.2, 1)';
                        ghost.style.left = `${rFrom.left + rFrom.width / 2}px`;
                        ghost.style.top = `${rFrom.top + rFrom.height / 2}px`;
                    });
                    setTimeout(() => {
                        ghost.remove();
                        source.classList.remove('drag-source');
                    }, 160);
                } else {
                    source.classList.remove('drag-source');
                }
                clearGesture();
            }
        } else {
            const dist = Math.hypot(event.clientX - startX, event.clientY - startY);
            clearGesture();
            if (dist < 12) {
                suppressClickUntil = performance.now() + 400;
                suppressedTarget = source;

                // Recall individual draft tile back to rack on click!
                if (source.classList.contains('board-cell') && source.classList.contains('draft')) {
                    const rackEl = document.querySelector('.rack');
                    if (rackEl) animateTileMove(source, rackEl);
                    send({type: 'return', cell: Number(source.dataset.cell)});
                    return;
                }
                suppressedTarget = source;

                // Tap-to-place: selected rack slot -> empty board cell
                const selectedRackSlot = document.querySelector('.rack-slot.selected');
                if (selectedRackSlot && source.classList.contains('board-cell') && !source.classList.contains('committed') && !source.classList.contains('draft')) {
                    animateTileMove(selectedRackSlot, source);
                    selectedRackSlot.classList.remove('selected');
                    selectedRackSlot.setAttribute('aria-pressed', 'false');
                    send({type: 'drop', cell: Number(source.dataset.cell), source: selectedRackSlot.dataset.source});
                    return;
                }

                // Selecting a rack slot
                if (source.classList.contains('rack-slot') && !source.classList.contains('used')) {
                    const wasSelected = source.classList.contains('selected');
                    document.querySelectorAll('.rack-slot.selected').forEach(s => {
                        s.classList.remove('selected');
                        s.setAttribute('aria-pressed', 'false');
                    });
                    if (!wasSelected) {
                        source.classList.add('selected');
                        source.setAttribute('aria-pressed', 'true');
                    }
                }

                // Normal click action
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
            closeSocket();
            return;
        }

        // Resume saved game
        const resumeBtn = target.closest('[data-resume-game]');
        if (resumeBtn) {
            const gid = resumeBtn.dataset.resumeGame || '';
            if (gid.startsWith('mp:')) {
                suppressSocketUntil = 0;
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

        // Recall individual draft tile back to rack on click!
        if (actionEl.classList.contains('board-cell') && actionEl.classList.contains('draft')) {
            const rackEl = document.querySelector('.rack');
            if (rackEl) animateTileMove(actionEl, rackEl);
            send({type: 'return', cell: Number(actionEl.dataset.cell)});
            return;
        }

        // Tap-to-place: selected rack slot -> empty board cell
        const selectedRackSlot = document.querySelector('.rack-slot.selected');
        if (selectedRackSlot && actionEl.classList.contains('board-cell') && !actionEl.classList.contains('committed') && !actionEl.classList.contains('draft')) {
            animateTileMove(selectedRackSlot, actionEl);
            selectedRackSlot.classList.remove('selected');
            selectedRackSlot.setAttribute('aria-pressed', 'false');
            send({type: 'drop', cell: Number(actionEl.dataset.cell), source: selectedRackSlot.dataset.source});
            return;
        }

        // Selecting a rack slot on click
        if (actionEl.classList.contains('rack-slot') && !actionEl.classList.contains('used')) {
            const wasSelected = actionEl.classList.contains('selected');
            document.querySelectorAll('.rack-slot.selected').forEach(s => {
                s.classList.remove('selected');
                s.setAttribute('aria-pressed', 'false');
            });
            if (!wasSelected) {
                actionEl.classList.add('selected');
                actionEl.setAttribute('aria-pressed', 'true');
            }
        }

        if (actionEl.dataset.action === 'shuffle') {
            shuffleRackAnimation();
            send({type: 'shuffle'});
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
            if (!t) continue;
            if (
                t.id === 'game-view' ||
                t.id === 'game-view-container' ||
                t.classList?.contains('board-frame') ||
                t.classList?.contains('board-shell') ||
                t.classList?.contains('scrabble-grid') ||
                t.classList?.contains('rack') ||
                t.classList?.contains('rack-panel') ||
                t.classList?.contains('play-area') ||
                (typeof t.closest === 'function' && t.closest('#game-view, #game-view-container'))
            ) {
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
        attributeFilter: ['data-busy', 'data-room-code', 'data-mp-version', 'data-sync-version'],
        subtree: true
    });
})();
