document.addEventListener('DOMContentLoaded', () => {
    // --- State variables ---
    let currentBlob = null;
    let currentFileName = null;
    let isPlaying = false;
    let isDraggingTimeline = false;

    // --- DOM Elements ---
    const form = document.getElementById('tts-form');
    
    // Inputs
    const textContent = document.getElementById('text_content');
    const charCounter = document.getElementById('char-counter');
    const charWarning = document.getElementById('char-warning');
    const btnClearText = document.getElementById('btn-clear-text');
    
    // File Upload
    const dropzone = document.getElementById('dropzone');
    const fileInput = document.getElementById('file');
    const fileFeedback = document.getElementById('file-feedback');
    const fileNameDisplay = document.getElementById('file-name');
    const btnRemoveFile = document.getElementById('btn-remove-file');
    
    // Sliders
    const rateInput = document.getElementById('rate');
    const pitchInput = document.getElementById('pitch');
    const volumeInput = document.getElementById('volume');
    const rateVal = document.getElementById('rate-val');
    const pitchVal = document.getElementById('pitch-val');
    const volumeVal = document.getElementById('volume-val');
    
    // Submit Button
    const btnSubmit = document.getElementById('btn-submit');
    const submitText = document.getElementById('submit-text');
    const submitIcon = document.getElementById('submit-icon');
    const submitSpinner = document.getElementById('submit-spinner');
    const statusMessage = document.getElementById('status-message');

    // Player Elements
    const playerSection = document.getElementById('player-section');
    const audio = document.getElementById('native-audio');
    
    // Timeline Controls
    const progressContainer = document.getElementById('progress-container');
    const progressPlayed = document.getElementById('progress-played');
    const progressBuffer = document.getElementById('progress-buffer');
    const progressThumb = document.getElementById('progress-thumb');
    const timeCurrent = document.getElementById('time-current');
    const timeTotal = document.getElementById('time-total');
    
    // Playback Buttons
    const btnPlayPause = document.getElementById('btn-play-pause');
    const iconPlayPause = document.getElementById('icon-play-pause');
    const btnRewind = document.getElementById('btn-rewind');
    const btnForward = document.getElementById('btn-forward');
    
    // Volume Controls
    const btnMute = document.getElementById('btn-mute');
    const playerVolume = document.getElementById('player-volume');
    const iconVolume = document.getElementById('icon-volume');
    
    // Final Actions
    const btnDownload = document.getElementById('btn-download');
    const btnShareWa = document.getElementById('btn-share-wa');

    // CSRF Token
    const csrfToken = document.querySelector('meta[name="csrf-token"]').getAttribute('content');

    // --- Helper Functions ---
    const formatTime = (seconds) => {
        if (isNaN(seconds)) return "00:00";
        const m = Math.floor(seconds / 60).toString().padStart(2, '0');
        const s = Math.floor(seconds % 60).toString().padStart(2, '0');
        return `${m}:${s}`;
    };

    const setStatus = (msg, type = 'info') => {
        statusMessage.textContent = msg;
        statusMessage.classList.remove('hidden', 'bg-red-50', 'text-red-600', 'bg-blue-50', 'text-blue-600', 'bg-zinc-50', 'text-zinc-600');
        if (type === 'error') {
            statusMessage.classList.add('bg-red-50', 'text-red-600');
        } else if (type === 'success') {
            statusMessage.classList.add('bg-green-50', 'text-green-600');
        } else {
            statusMessage.classList.add('bg-blue-50', 'text-blue-600');
        }
    };

    // --- Textarea Logic ---
    textContent.addEventListener('input', () => {
        const len = textContent.value.length;
        charCounter.textContent = `${len} caracteres`;
        
        if (len > 5000) {
            charWarning.classList.remove('hidden');
        } else {
            charWarning.classList.add('hidden');
        }
    });

    btnClearText.addEventListener('click', () => {
        textContent.value = '';
        textContent.dispatchEvent(new Event('input'));
    });

    // --- File Drag & Drop Logic ---
    dropzone.addEventListener('click', (e) => {
        if (e.target !== btnRemoveFile && !btnRemoveFile.contains(e.target)) {
            fileInput.click();
        }
    });

    const handleFile = (file) => {
        if (file) {
            fileFeedback.classList.remove('hidden');
            fileNameDisplay.textContent = file.name;
        } else {
            fileFeedback.classList.add('hidden');
            fileInput.value = '';
        }
    };

    fileInput.addEventListener('change', (e) => handleFile(e.target.files[0]));

    btnRemoveFile.addEventListener('click', (e) => {
        e.stopPropagation(); // Avoid triggering dropzone click
        handleFile(null);
    });

    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(ev => {
        dropzone.addEventListener(ev, (e) => {
            e.preventDefault();
            e.stopPropagation();
        });
    });

    ['dragenter', 'dragover'].forEach(ev => {
        dropzone.addEventListener(ev, () => dropzone.classList.add('drag-active'));
    });

    ['dragleave', 'drop'].forEach(ev => {
        dropzone.addEventListener(ev, () => dropzone.classList.remove('drag-active'));
    });

    dropzone.addEventListener('drop', (e) => {
        const droppedFiles = e.dataTransfer.files;
        if (droppedFiles.length) {
            fileInput.files = droppedFiles;
            handleFile(droppedFiles[0]);
        }
    });

    // --- Sliders UI Updates ---
    rateInput.addEventListener('input', (e) => rateVal.textContent = `${e.target.value > 0 ? '+' : ''}${e.target.value}%`);
    pitchInput.addEventListener('input', (e) => pitchVal.textContent = `${e.target.value > 0 ? '+' : ''}${e.target.value}Hz`);
    volumeInput.addEventListener('input', (e) => volumeVal.textContent = `${e.target.value > 0 ? '+' : ''}${e.target.value}%`);


    // --- Form Submission Logic ---
    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        // Validation
        if (!textContent.value.trim() && !fileInput.files[0]) {
            setStatus("Escribe texto o sube un archivo.", "error");
            return;
        }

        // CRITICAL FOR iOS (WebKit): "Unlock" the audio element on user gesture
        // chrome/edge on iOS require a direct user interaction to play audio later from an async fetch
        audio.play().then(() => {
            audio.pause();
            audio.currentTime = 0;
        }).catch(() => { /* Initial unlock may fail if blocked, we try again after fetch */ });

        // Set Loading State
        btnSubmit.disabled = true;
        submitText.textContent = "Procesando...";
        submitIcon.classList.add('hidden');
        submitSpinner.classList.remove('hidden');
        setStatus("Generando audio, por favor espera...", "info");
        playerSection.classList.add('hidden'); // Hide old player
        
        const formData = new FormData(form);
        // Explicitly ensuring csrf_token is in the formData for certain mobile browsers
        if (!formData.has('csrf_token') && csrfToken) {
            formData.append('csrf_token', csrfToken);
        }

        try {
            const response = await fetch('/api/generate', {
                method: 'POST',
                headers: {
                    'X-CSRFToken': csrfToken
                },
                body: formData
            });
            
            const contentType = response.headers.get("content-type");
            let data;
            
            if (contentType && contentType.includes("application/json")) {
                data = await response.json();
            } else {
                // Return fallback error if it's an HTML page (likely 413 or 500)
                throw new Error(`Error del servidor (${response.status}). Inténtalo de nuevo más tarde.`);
            }
            
            if (!response.ok) {
                throw new Error(data.error || "Ocurrió un error inesperado.");
            }

            // Success
            setStatus("¡Audio generado con éxito!", "success");
            
            // Setup Player
            // For WebKit (iOS), explicitly calling .load() after setting .src is more reliable
            audio.src = data.audio_url;
            audio.load();
            
            btnDownload.href = data.download_url;
            currentFileName = data.filename;
            
            // Show Player
            playerSection.classList.remove('hidden');
            
            // Auto play (Now more likely to work because we "unlocked" it above)
            const playPromise = audio.play();
            if (playPromise !== undefined) {
                playPromise.catch(() => {
                    console.info("Auto-play blocked by iOS WebKit, needs manual play.");
                    setStatus("Audio listo. Pulsa el botón de Play para escuchar.", "success");
                });
            }

        } catch (error) {
            setStatus(error.message, "error");
        } finally {
            // Restore Submit Button
            btnSubmit.disabled = false;
            submitText.textContent = "Transformar a Audio";
            submitSpinner.classList.add('hidden');
            submitIcon.classList.remove('hidden');
        }
    });

    // --- Audio Player Logic ---
    
    // Play/Pause toggle
    const togglePlay = () => {
        if (audio.paused) {
            audio.play();
        } else {
            audio.pause();
        }
    };
    
    btnPlayPause.addEventListener('click', togglePlay);
    
    audio.addEventListener('play', () => {
        isPlaying = true;
        iconPlayPause.classList.replace('ph-play', 'ph-pause');
    });
    
    audio.addEventListener('pause', () => {
        isPlaying = false;
        iconPlayPause.classList.replace('ph-pause', 'ph-play');
    });

    audio.addEventListener('ended', () => {
        isPlaying = false;
        iconPlayPause.classList.replace('ph-pause', 'ph-play');
        audio.currentTime = 0; // Reset
    });

    // Jump buttons
    btnRewind.addEventListener('click', () => {
        audio.currentTime = Math.max(0, audio.currentTime - 10);
    });

    btnForward.addEventListener('click', () => {
        audio.currentTime = Math.min(audio.duration || 0, audio.currentTime + 10);
    });
    
    // Progress / Timeline Logic
    audio.addEventListener('loadedmetadata', () => {
        timeTotal.textContent = formatTime(audio.duration);
    });

    audio.addEventListener('timeupdate', () => {
        if (!audio.duration) return;
        timeCurrent.textContent = formatTime(audio.currentTime);
        
        if (!isDraggingTimeline) {
            const progressPercent = (audio.currentTime / audio.duration) * 100;
            progressPlayed.style.width = `${progressPercent}%`;
            progressThumb.style.left = `${progressPercent}%`;
        }
        
        // Show buffer
        if (audio.buffered.length > 0) {
            const bufferPercent = (audio.buffered.end(audio.buffered.length - 1) / audio.duration) * 100;
            progressBuffer.style.width = `${bufferPercent}%`;
        }
    });

    // Timeline Interaction (Seek)
    const updateProgressFromEvent = (e) => {
        const rect = progressContainer.getBoundingClientRect();
        const pos = Math.max(0, Math.min(e.clientX - rect.left, rect.width));
        const percentage = pos / rect.width;
        
        progressPlayed.style.width = `${percentage * 100}%`;
        progressThumb.style.left = `${percentage * 100}%`;
        
        return percentage;
    };

    progressContainer.addEventListener('mousedown', (e) => {
        if (!audio.src) return;
        isDraggingTimeline = true;
        updateProgressFromEvent(e);
    });

    document.addEventListener('mousemove', (e) => {
        if (isDraggingTimeline) {
            updateProgressFromEvent(e);
        }
    });

    document.addEventListener('mouseup', (e) => {
        if (isDraggingTimeline) {
            isDraggingTimeline = false;
            const percentage = updateProgressFromEvent(e);
            audio.currentTime = percentage * audio.duration;
        }
    });
    
    // Touch support for progress bar
    progressContainer.addEventListener('touchstart', (e) => {
        if (!audio.src) return;
        isDraggingTimeline = true;
        updateProgressFromEvent(e.touches[0]);
    }, {passive:true});
    document.addEventListener('touchmove', (e) => {
        if (isDraggingTimeline) {
            updateProgressFromEvent(e.touches[0]);
        }
    }, {passive:true});
    document.addEventListener('touchend', (e) => {
        if (isDraggingTimeline) {
            isDraggingTimeline = false;
            const percentage = parseFloat(progressPlayed.style.width) / 100;
            audio.currentTime = percentage * audio.duration;
        }
    });

    // Volume Control
    playerVolume.addEventListener('input', (e) => {
        const vol = e.target.value;
        audio.volume = vol;
        
        if (vol == 0) {
            iconVolume.classList.replace('ph-speaker-high', 'ph-speaker-x');
            iconVolume.classList.replace('ph-speaker-low', 'ph-speaker-x');
        } else if (vol < 0.5) {
            iconVolume.classList.replace('ph-speaker-high', 'ph-speaker-low');
            iconVolume.classList.replace('ph-speaker-x', 'ph-speaker-low');
        } else {
            iconVolume.classList.replace('ph-speaker-low', 'ph-speaker-high');
            iconVolume.classList.replace('ph-speaker-x', 'ph-speaker-high');
        }
    });
    
    let lastVolume = 1;
    btnMute.addEventListener('click', () => {
        if (audio.volume > 0) {
            lastVolume = audio.volume;
            playerVolume.value = 0;
            playerVolume.dispatchEvent(new Event('input'));
        } else {
            playerVolume.value = lastVolume || 1;
            playerVolume.dispatchEvent(new Event('input'));
        }
    });

    // --- Social Sharing ---
    btnShareWa.addEventListener('click', () => {
        if (!audio.src) return;
        
        // El enlace local o URL real
        const currentUrl = window.location.origin;
        // The downloaded MP3 must be shared, or the current website URL
        const text = encodeURIComponent(`Escucha este audio generado automáticamente con TTS Webapp: ¡Descárgalo o compártelo!`);
        window.open(`https://wa.me/?text=${text} ${currentUrl}`, '_blank');
    });

});
