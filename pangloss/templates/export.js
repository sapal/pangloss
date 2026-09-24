        const metadata = __METADATA_JSON__;
        const audioData = __AUDIO_DATA_JSON__;
        const scrollContainer = document.getElementById('scrollContainer');
        const storyEl = document.getElementById('story');
        const playBtn = document.getElementById('playToggle');
        const statusEl = document.getElementById('status');
        const player = document.getElementById('player');
        const prevBtn = document.getElementById('prevBtn');
        const nextBtn = document.getElementById('nextBtn');
        const drawer = document.getElementById('drawer');
        const overlay = document.getElementById('overlay');
        const drawerToggle = document.getElementById('drawerToggle');
        const rewindBtn = document.getElementById('rewindBtn');
        const closeDrawer = document.getElementById('closeDrawer');
        
        const prevChunkBtn = document.getElementById('prevChunkBtn');
        const nextChunkBtn = document.getElementById('nextChunkBtn');

        let currentId = null;
        let isPlaying = false;
        let currentActiveChunk = null;

        const PLAY_SVG = __PLAY_SVG_JSON__;
        const PAUSE_SVG = __PAUSE_SVG_JSON__;

        function md(text) {
            if (!text) return "";
            // Headers
            text = text.replace(/^### (.*$)/gim, '<h3>$1</h3>');
            text = text.replace(/^## (.*$)/gim, '<h2>$1</h2>');
            text = text.replace(/^# (.*$)/gim, '<h1>$1</h1>');
            // Rulers
            text = text.replace(/^---+$|^___+$/gim, '<hr>');
            // Bold
            text = text.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
            text = text.replace(/__(.*?)__/g, '<strong>$1</strong>');
            // Italics
            text = text.replace(/\*(.*?)\*/g, '<em>$1</em>');
            text = text.replace(/_(.*?)_/g, '<em>$1</em>');
            return text;
        }

        function toggleTooltip(e, el) {
            if (e) e.stopPropagation();
            const wasActive = el.classList.contains('active-tooltip');
            document.querySelectorAll('.word.active-tooltip').forEach(w => {
                w.classList.remove('active-tooltip');
            });
            if (!wasActive) {
                el.classList.add('active-tooltip');
            }
        }

        document.addEventListener('click', function(e) {
            if (!e.target.closest('.word')) {
                document.querySelectorAll('.word.active-tooltip').forEach(w => {
                    w.classList.remove('active-tooltip');
                });
            }
        });

        function applyWords(html, sortedWords) {
            if (!html || !sortedWords || sortedWords.length === 0) return html;
            let result = html;
            const tagPlaceholders = [];
            result = result.replace(/<[^>]+>/g, (tag) => {
                const idx = tagPlaceholders.length;
                tagPlaceholders.push(tag);
                return `\uE000TAG_${idx}_\uE001`;
            });

            const wordPlaceholders = [];
            sortedWords.forEach(dw => {
                const anchors = dw.anchors || [dw.word];
                const sortedAnchors = [...anchors].sort((a, b) => b.length - a.length);
                sortedAnchors.forEach(anchor => {
                    const escaped = anchor.replace(/[.*+?^${}()[\]\\]/g, '\\$&');
                    const regex = new RegExp("\\b" + escaped + "\\b", 'gi');
                    result = result.replace(regex, (match) => {
                        const idx = wordPlaceholders.length;
                        const tooltipHtml = `<span class="word" onclick="toggleTooltip(event, this)">${match}<div class="tooltip" onclick="event.stopPropagation()"><strong>${dw.word}</strong>: ${dw.explanation}</div></span>`;
                        wordPlaceholders.push(tooltipHtml);
                        return `\uE000WORD_${idx}_\uE001`;
                    });
                });
            });

            result = result.replace(/\uE000WORD_(\d+)_\uE001/g, (_, idx) => wordPlaceholders[idx]);
            result = result.replace(/\uE000TAG_(\d+)_\uE001/g, (_, idx) => tagPlaceholders[idx]);
            return result;
        }

        function renderTransRow(p, rowIdx, rawText, sortedWords, rowStart, rowEnd) {
            if (!rawText) return "";
            let cleanText = rawText.replace(/<[a-zA-Z\s_-]+>/g, "");
            const chunks = p.chunks;
            if (!chunks || chunks.length === 0) {
                let html = md(cleanText);
                return applyWords(html, sortedWords);
            }

            const overlapping = chunks.filter(c => Math.max(rowStart, c.start_char) < Math.min(rowEnd, c.end_char));
            if (overlapping.length === 0) {
                let html = md(cleanText);
                return applyWords(html, sortedWords);
            }

            if (overlapping.length === 1) {
                const c = overlapping[0];
                const hMatch = cleanText.match(/^(#+)\s*(.*$)/);
                if (hMatch) {
                    const level = hMatch[1].length;
                    let hContent = md(hMatch[2]);
                    hContent = applyWords(hContent, sortedWords);
                    return `<h${level}><span class="chunk-target chunk-p${p.id}-c${c.chunk_index}" data-para-id="${p.id}" data-chunk-idx="${c.chunk_index}" onclick="seekToChunk(event, ${p.id}, ${c.chunk_index})">${hContent}</span></h${level}>`;
                } else {
                    let content = md(cleanText);
                    content = applyWords(content, sortedWords);
                    return `<span class="chunk-target chunk-p${p.id}-c${c.chunk_index}" data-para-id="${p.id}" data-chunk-idx="${c.chunk_index}" onclick="seekToChunk(event, ${p.id}, ${c.chunk_index})">${content}</span>`;
                }
            } else {
                const pieces = overlapping.map(c => {
                    const oStart = Math.max(rowStart, c.start_char);
                    const oEnd = Math.min(rowEnd, c.end_char);
                    const segText = cleanText.slice(oStart - rowStart, oEnd - rowStart);
                    let segHtml = md(segText);
                    segHtml = applyWords(segHtml, sortedWords);
                    return `<span class="chunk-target chunk-p${p.id}-c${c.chunk_index}" data-para-id="${p.id}" data-chunk-idx="${c.chunk_index}" onclick="seekToChunk(event, ${p.id}, ${c.chunk_index})">${segHtml}</span>`;
                });
                return pieces.join('');
            }
        }

        function render() {
            storyEl.innerHTML = metadata.paragraphs.map(p => {
                const speakersList = Array.from(new Set(p.turns.map(t => t.speaker)));
                const speakers = speakersList.length > 0 ? speakersList.join(' • ') : 'Narrator';
                
                const origParas = p.originalText.split('\n\n');
                const transParas = p.translatedText.split('\n\n');
                const maxParas = Math.max(origParas.length, transParas.length);

                const sortedWords = [...metadata.difficultWords].sort((a,b) => b.word.length - a.word.length);

                let pPos = 0;
                const alignedContent = Array.from({ length: maxParas }).map((_, i) => {
                    let origPara = (origParas[i] || "").replace(/<[a-zA-Z\s_-]+>/g, "");
                    let transPara = (transParas[i] || "");

                    const rowStart = pPos;
                    const rowEnd = pPos + transPara.length;
                    pPos = rowEnd + 2;

                    const renderedTrans = renderTransRow(p, i, transPara, sortedWords, rowStart, rowEnd);

                    return `
                        <div class="grid grid-cols-1 md:grid-cols-2 gap-12 items-start mb-8 last:mb-0">
                            <div id="orig-${p.id}-${i}" class="text-base md:text-xl leading-relaxed font-serif opacity-70 transition-all duration-300 text-content">${md(origPara)}</div>
                            <div id="trans-${p.id}-${i}" class="text-base md:text-xl leading-relaxed font-serif transition-all duration-300 text-content">${renderedTrans}</div>
                        </div>
                    `;
                }).join('');

                return `
                    <div class="group/row border-b border-ink/5 pt-12 pb-12 transition-all first:pt-0" id="section-${p.id}">
                        <div class="flex items-center gap-4 mb-8">
                            <span class="text-[10px] uppercase tracking-[2px] font-bold text-muted border-b border-accent/30 pb-1">${speakers}</span>
                            <button onclick="playPara(${p.id})" class="w-8 h-8 rounded-full bg-accent/10 flex items-center justify-center hover:bg-accent hover:text-paper transition-all">
                                <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg>
                            </button>
                        </div>
                        <div id="trans-${p.id}" onclick="playPara(${p.id})" class="cursor-pointer">
                            ${alignedContent}
                        </div>
                    </div>
                `;
            }).join('');

            document.getElementById('vocabList').innerHTML = metadata.difficultWords.map(dw => `
                <div class="group border-b border-ink/5 pb-6 last:border-0 hover:translate-x-1 transition-transform">
                    <p class="text-2xl font-serif font-bold mb-2">${dw.word}</p>
                    <p class="text-sm text-ink/70 font-serif italic leading-relaxed">${dw.explanation}</p>
                </div>
            `).join('');

            document.getElementById('castList').innerHTML = metadata.characters.map(char => `
                <div class="flex gap-6">
                    <div class="w-12 h-12 bg-paper border border-ink/10 rounded-full flex items-center justify-center flex-shrink-0 shadow-sm">
                        <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#5A5A40" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 5L6 9H2v6h4l5 4V5z"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14"/><path d="M15.54 8.46a5 5 0 0 1 0 7.07"/></svg>
                    </div>
                    <div>
                        <p class="text-xl font-serif font-bold mb-1">${char.name}</p>
                        <p class="text-xs text-ink/60 font-serif italic leading-relaxed mb-3">${char.description}</p>
                        <div class="flex flex-wrap gap-2">
                            <span class="text-[9px] uppercase tracking-[2px] font-bold px-3 py-1 bg-accent text-paper rounded-full">Voice • ${char.voice}</span>
                            <span class="text-[9px] uppercase tracking-[1px] font-bold px-3 py-1 bg-ink/5 text-ink/70 rounded-full italic hover:bg-ink/10 transition-colors cursor-default">${char.voiceProfile}</span>
                        </div>
                    </div>
                </div>
            `).join('');

            document.querySelectorAll('[id^="section-"]').forEach(el => observer.observe(el));
        }

        function openDrawer() {
            drawer.classList.add('active');
            overlay.classList.add('opacity-100', 'pointer-events-auto');
        }

        if (drawerToggle) drawerToggle.onclick = openDrawer;

        closeDrawer.onclick = overlay.onclick = () => {
            drawer.classList.remove('active');
            overlay.classList.remove('opacity-100', 'pointer-events-auto');
        };

        if (rewindBtn) {
            rewindBtn.onclick = () => {
                if (player && player.src) {
                    player.currentTime = Math.max(0, player.currentTime - 10);
                }
            };
        }

        function getActiveChunkInfo() {
            if (currentId === null) return null;
            const p = metadata.paragraphs.find(para => para.id === currentId);
            if (!p || !p.chunks || p.chunks.length === 0) return null;
            const t = player.currentTime;
            let idx = p.chunks.findIndex(c => t >= c.start_sec && t < c.end_sec);
            if (idx === -1) {
                if (t >= p.chunks[p.chunks.length - 1].end_sec) {
                    idx = p.chunks.length - 1;
                } else {
                    for (let i = 0; i < p.chunks.length; i++) {
                        if (t < p.chunks[i].end_sec) {
                            idx = i;
                            break;
                        }
                    }
                    if (idx === -1) idx = 0;
                }
            }
            return { p, chunks: p.chunks, chunkIndex: idx, chunk: p.chunks[idx] };
        }

        function highlightActiveChunk(chunkIdx) {
            if (currentActiveChunk === chunkIdx && document.querySelector(`.chunk-p${currentId}-c${chunkIdx}.active-chunk`)) {
                return;
            }
            document.querySelectorAll('.active-chunk').forEach(el => {
                el.classList.remove('active-chunk');
            });
            if (chunkIdx !== null && currentId !== null) {
                const els = document.querySelectorAll(`.chunk-p${currentId}-c${chunkIdx}`);
                els.forEach(el => {
                    el.classList.add('active-chunk');
                });
                currentActiveChunk = chunkIdx;
            } else {
                currentActiveChunk = null;
            }
        }

        function scrollToActiveChunk(chunk, smooth = true, force = false) {
            if (currentId === null) return false;
            const els = document.querySelectorAll(`.chunk-p${currentId}-c${chunk.chunk_index}`);
            if (els.length === 0) return false;

            const firstEl = els[0];
            const lastEl = els[els.length - 1];
            const firstRect = firstEl.getBoundingClientRect();
            const lastRect = lastEl.getBoundingClientRect();
            const containerRect = scrollContainer.getBoundingClientRect();

            const chunkDur = (chunk.end_sec - chunk.start_sec) || 1;
            const chunkProgress = Math.max(0, Math.min(1, (player.currentTime - chunk.start_sec) / chunkDur));

            const topY = firstRect.top;
            const bottomY = lastRect.bottom;
            const totalHeight = Math.max(firstRect.height, bottomY - topY);

            const pointY = topY - containerRect.top + chunkProgress * totalHeight;
            const margin = 150;
            if (force || pointY < margin || pointY > scrollContainer.clientHeight - margin) {
                const targetScrollTop = scrollContainer.scrollTop + pointY - scrollContainer.clientHeight / 2;
                scrollContainer.scrollTo({ top: targetScrollTop, behavior: smooth ? 'smooth' : 'auto' });
                return true;
            }
            return false;
        }

        function scrollToActiveText(smooth = true, force = false) {
            if (currentId === null) return false;
            const p = metadata.paragraphs.find(para => para.id === currentId);
            if (!p) return false;

            const progress = player.duration ? (player.currentTime / player.duration) : 0;
            const origParas = p.originalText.split('\n\n');
            const transParas = p.translatedText.split('\n\n');
            const maxParas = Math.max(origParas.length, transParas.length);

            const totalLen = origParas.reduce((acc, text) => acc + text.length, 0);
            let cumulativeLen = 0;
            let activeSubIndex = 0;
            if (totalLen > 0) {
                const targetLen = progress * totalLen;
                for (let i = 0; i < origParas.length; i++) {
                    cumulativeLen += origParas[i].length;
                    if (targetLen <= cumulativeLen) {
                        activeSubIndex = i;
                        break;
                    }
                }
            }
            if (activeSubIndex >= maxParas) {
                activeSubIndex = maxParas - 1;
            }

            const transEl = document.getElementById(`trans-${currentId}-${activeSubIndex}`);
            if (!transEl) return false;

            let startLen = 0;
            for (let i = 0; i < activeSubIndex; i++) {
                if (origParas[i]) {
                    startLen += origParas[i].length;
                }
            }
            const activeParaLen = origParas[activeSubIndex] ? origParas[activeSubIndex].length : 0;
            const endLen = startLen + activeParaLen;
            const startProgress = startLen / (totalLen || 1);
            const endProgress = endLen / (totalLen || 1);

            let subProgress = 0;
            if (endProgress > startProgress) {
                subProgress = (progress - startProgress) / (endProgress - startProgress);
                subProgress = Math.max(0, Math.min(1, subProgress));
            }

            const rect = transEl.getBoundingClientRect();
            const containerRect = scrollContainer.getBoundingClientRect();
            const pointY = rect.top - containerRect.top + subProgress * rect.height;

            const margin = 150;
            if (force || pointY < margin || pointY > scrollContainer.clientHeight - margin) {
                const targetScrollTop = scrollContainer.scrollTop + pointY - scrollContainer.clientHeight / 2;
                scrollContainer.scrollTo({ top: targetScrollTop, behavior: smooth ? 'smooth' : 'auto' });
                return true;
            }
            return false;
        }

        function seekToChunk(e, paraId, chunkIdx) {
            if (e) e.stopPropagation();
            if (currentId !== paraId) {
                playPara(paraId, true);
            }
            const p = metadata.paragraphs.find(para => para.id === paraId);
            if (p && p.chunks && p.chunks[chunkIdx]) {
                const c = p.chunks[chunkIdx];
                player.currentTime = c.start_sec;
                highlightActiveChunk(c.chunk_index);
                scrollToActiveChunk(c, true, true);
                if (!isPlaying) {
                    player.play();
                    isPlaying = true;
                    updateUI();
                }
            }
        }

        function prevChunk() {
            const info = getActiveChunkInfo();
            if (!info) {
                const pIndex = metadata.paragraphs.findIndex(p => p.id === currentId);
                if (pIndex > 0) playPara(metadata.paragraphs[pIndex - 1].id);
                return;
            }

            if (player.currentTime > info.chunk.start_sec + 1.5) {
                player.currentTime = info.chunk.start_sec;
                highlightActiveChunk(info.chunk.chunk_index);
                scrollToActiveChunk(info.chunk, true, true);
            } else if (info.chunkIndex > 0) {
                const prevC = info.chunks[info.chunkIndex - 1];
                player.currentTime = prevC.start_sec;
                highlightActiveChunk(prevC.chunk_index);
                scrollToActiveChunk(prevC, true, true);
            } else {
                const pIndex = metadata.paragraphs.findIndex(p => p.id === currentId);
                if (pIndex > 0) {
                    const prevP = metadata.paragraphs[pIndex - 1];
                    playPara(prevP.id, true);
                    if (prevP.chunks && prevP.chunks.length > 0) {
                        const lastC = prevP.chunks[prevP.chunks.length - 1];
                        player.currentTime = lastC.start_sec;
                        highlightActiveChunk(lastC.chunk_index);
                        scrollToActiveChunk(lastC, true, true);
                    }
                } else {
                    player.currentTime = 0;
                    highlightActiveChunk(0);
                    scrollToActiveChunk(info.chunk, true, true);
                }
            }
        }

        function nextChunk() {
            const info = getActiveChunkInfo();
            if (!info) {
                const pIndex = metadata.paragraphs.findIndex(p => p.id === currentId);
                if (pIndex < metadata.paragraphs.length - 1) playPara(metadata.paragraphs[pIndex + 1].id);
                return;
            }

            if (info.chunkIndex < info.chunks.length - 1) {
                const nextC = info.chunks[info.chunkIndex + 1];
                player.currentTime = nextC.start_sec;
                highlightActiveChunk(nextC.chunk_index);
                scrollToActiveChunk(nextC, true, true);
                if (!isPlaying) {
                    player.play();
                    isPlaying = true;
                    updateUI();
                }
            } else {
                const pIndex = metadata.paragraphs.findIndex(p => p.id === currentId);
                if (pIndex < metadata.paragraphs.length - 1) {
                    playPara(metadata.paragraphs[pIndex + 1].id);
                }
            }
        }

        if (prevChunkBtn) prevChunkBtn.onclick = prevChunk;
        if (nextChunkBtn) nextChunkBtn.onclick = nextChunk;

        let lastScrollTime = 0;
        player.addEventListener('timeupdate', () => {
            if (!isPlaying || currentId === null) return;

            const info = getActiveChunkInfo();
            if (info) {
                highlightActiveChunk(info.chunkIndex);
            }

            const now = Date.now();
            if (now - lastScrollTime < 800) return;
            
            let didScroll = false;
            if (info) {
                didScroll = scrollToActiveChunk(info.chunk, true, false);
            } else {
                didScroll = scrollToActiveText(true, false);
            }
            if (didScroll) {
                lastScrollTime = now;
            }
        });

        function playPara(id, restart = true) {
            if (restart || player.src !== audioData[id]) {
                player.src = audioData[id];
            }
            currentId = id;
            player.play();
            isPlaying = true;
            currentActiveChunk = null;
            highlightActiveChunk(0);
            updateUI();
        }

        const observer = new IntersectionObserver((entries) => {
            if (isPlaying) return;
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    const id = parseInt(entry.target.id.replace('section-', ''));
                    if (currentId !== id) {
                        currentId = id;
                        updateUI(false);
                    }
                }
            });
        }, { threshold: 0.5 });

        function updateUI(autoScroll = true) {
            document.querySelectorAll('[id^="section-"]').forEach(el => {
                el.classList.remove('bg-accent/5', 'ring-1', 'ring-accent/10', 'shadow-sm', 'p-8', '-mx-8', 'rounded-2xl');
            });
            document.querySelectorAll('[id^="orig-"]').forEach(el => el.classList.add('opacity-40'));

            if (currentId !== null) {
                const section = document.getElementById('section-' + currentId);
                if (section) {
                    section.classList.add('bg-accent/5', 'ring-1', 'ring-accent/10', 'shadow-sm', 'p-8', '-mx-8', 'rounded-2xl');
                    section.querySelectorAll('[id^="orig-"]').forEach(el => el.classList.remove('opacity-40'));
                    if (autoScroll) {
                        const info = getActiveChunkInfo();
                        if (info) {
                            highlightActiveChunk(info.chunkIndex);
                            scrollToActiveChunk(info.chunk, true, true);
                        } else {
                            scrollToActiveText(true, true);
                        }
                    }
                }
                statusEl.innerText = `__CHAPTER_LABEL__ ` + currentId;
                if (window.location.hash !== '#section-' + currentId) {
                    history.replaceState(null, null, '#section-' + currentId);
                }
            } else {
                highlightActiveChunk(null);
            }
            playBtn.innerHTML = isPlaying ? PAUSE_SVG : PLAY_SVG;
            
            const index = metadata.paragraphs.findIndex(p => p.id === currentId);
            prevBtn.disabled = index <= 0;
            nextBtn.disabled = index >= metadata.paragraphs.length - 1 && index !== -1;
        }

        playBtn.onclick = () => {
            if (isPlaying) {
                player.pause();
                isPlaying = false;
            } else {
                if (currentId !== null && player.src === audioData[currentId]) {
                    player.play();
                    isPlaying = true;
                } else {
                    const nextId = currentId !== null ? currentId : metadata.paragraphs[0].id;
                    playPara(nextId);
                }
            }
            updateUI();
        };

        prevBtn.onclick = () => {
            const index = metadata.paragraphs.findIndex(p => p.id === currentId);
            if (index > 0) playPara(metadata.paragraphs[index - 1].id);
        };

        nextBtn.onclick = () => {
            const index = metadata.paragraphs.findIndex(p => p.id === currentId);
            if (index < metadata.paragraphs.length - 1) playPara(metadata.paragraphs[index + 1].id);
        };

        player.onended = () => {
            const index = metadata.paragraphs.findIndex(p => p.id === currentId);
            if (index < metadata.paragraphs.length - 1) {
                playPara(metadata.paragraphs[index + 1].id);
            } else {
                isPlaying = false;
                currentId = null;
                highlightActiveChunk(null);
                updateUI();
                statusEl.innerText = '__FINISHED_LABEL__';
            }
        };

        window.addEventListener('load', () => {
          render();
          const hash = window.location.hash;
          if (hash.startsWith('#section-')) {
              const id = parseInt(hash.replace('#section-', ''));
              if (!isNaN(id)) currentId = id;
          }
          updateUI(true);
        });
        // Initial render for immediate visibility
        render();
