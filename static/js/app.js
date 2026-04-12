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

    // --- Tab Switching Logic ---
    const tabBtns = document.querySelectorAll('.tab-btn');
    const tabContents = document.querySelectorAll('.tab-content');

    tabBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            const target = btn.getAttribute('data-target');
            
            // Update buttons
            tabBtns.forEach(b => {
                b.classList.remove('bg-white', 'shadow-sm', 'text-blue-600');
                b.classList.add('text-slate-500', 'hover:text-slate-700');
                const icon = b.querySelector('i');
                if (icon) icon.classList.replace('ph-fill', 'ph');
            });
            
            btn.classList.add('bg-white', 'shadow-sm', 'text-blue-600');
            btn.classList.remove('text-slate-500', 'hover:text-slate-700');
            const activeIcon = btn.querySelector('i');
            if (activeIcon) activeIcon.classList.replace('ph', 'ph-fill');

            // Update contents
            tabContents.forEach(content => {
                content.classList.add('hidden');
                content.classList.remove('block');
            });
            document.getElementById(target).classList.remove('hidden');
            document.getElementById(target).classList.add('block');
        });
    });

    // --- Audio to Text (STT) Logic ---
    
    // DOM Elements for STT
    const sttFile = document.getElementById('stt-file');
    const sttDropzone = document.getElementById('stt-dropzone');
    const sttFileFeedback = document.getElementById('stt-file-feedback');
    const sttFileName = document.getElementById('stt-file-name');
    const btnRemoveSttFile = document.getElementById('btn-remove-stt-file');
    
    const btnRecord = document.getElementById('btn-record');
    const btnStop = document.getElementById('btn-stop');
    const recorderPulse = document.getElementById('recorder-pulse');
    const recordStatus = document.getElementById('record-status');
    const recordTimerText = document.getElementById('record-timer');
    const sttRecordSizeDisplay = document.getElementById('stt-record-size');
    const btnPause = document.getElementById('btn-pause');
    const btnResume = document.getElementById('btn-resume');
    const btnDiscard = document.getElementById('btn-discard');
    
    // STT Player Elements
    const sttPlayerSection = document.getElementById('stt-player-section');
    const sttAudio = document.getElementById('stt-audio');
    const sttBtnPlayPause = document.getElementById('stt-btn-play-pause');
    const sttIconPlayPause = document.getElementById('stt-icon-play-pause');
    const sttBtnRewind = document.getElementById('stt-btn-rewind');
    const sttBtnForward = document.getElementById('stt-btn-forward');
    const sttProgressContainer = document.getElementById('stt-progress-container');
    const sttProgressPlayed = document.getElementById('stt-progress-played');
    const sttProgressThumb = document.getElementById('stt-progress-thumb');
    const sttTimeCurrent = document.getElementById('stt-time-current');
    const sttTimeTotal = document.getElementById('stt-time-total');
    const btnDownloadRecorded = document.getElementById('btn-download-recorded');
    const sttSizeWarning = document.getElementById('stt-size-warning');
    
    const btnTranscribe = document.getElementById('btn-transcribe');
    const transcribeText = document.getElementById('transcribe-text');
    const transcribeIcon = document.getElementById('transcribe-icon');
    const transcribeSpinner = document.getElementById('transcribe-spinner');
    const sttStatus = document.getElementById('stt-status');
    
    const sttResultArea = document.getElementById('stt-result-area');
    const sttOutput = document.getElementById('stt-output');
    const sttCharCounter = document.getElementById('stt-char-counter');
    const btnCopyStt = document.getElementById('btn-copy-stt');
    const btnDownloadStt = document.getElementById('btn-download-stt');

    let mediaRecorder = null;
    let audioChunks = [];
    let recordTimerInterval = null;
    let recordingStartTime = 0;
    let pausedStartTime = 0;
    let totalPausedTime = 0;
    let recordedBlob = null;
    let sttSelectedFile = null;
    let recordingMimeType = 'audio/webm'; 
    let isSttDragging = false;

    // Helper to find supported MIME type
    const getSupportedMimeType = () => {
        const types = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/aac', 'audio/ogg;codecs=opus'];
        for (const type of types) {
            if (MediaRecorder.isTypeSupported(type)) return type;
        }
        return '';
    };

    const setSttStatus = (msg, type = 'info') => {
        sttStatus.textContent = msg;
        sttStatus.classList.remove('hidden', 'bg-red-50', 'text-red-600', 'bg-blue-50', 'text-blue-600', 'bg-green-50', 'text-green-700');
        if (type === 'error') sttStatus.classList.add('bg-red-50', 'text-red-600');
        else if (type === 'success') sttStatus.classList.add('bg-green-50', 'text-green-700');
        else sttStatus.classList.add('bg-blue-50', 'text-blue-600');
    };

    const setRecorderUIState = (state) => {
        // Hide all secondary buttons by default
        btnStop.classList.add('hidden');
        btnPause.classList.add('hidden');
        btnResume.classList.add('hidden');
        btnDiscard.classList.add('hidden');
        
        // Reset styles
        btnRecord.classList.remove('animate-pulse', 'bg-red-500', 'text-white', 'opacity-50');
        btnRecord.disabled = false;
        recorderPulse.classList.add('hidden');

        switch(state) {
            case 'idle':
                recordStatus.textContent = "Grabar nota de voz";
                recordTimerText.textContent = "00:00";
                break;
            case 'recording':
                btnRecord.classList.add('animate-pulse', 'bg-red-50', 'text-red-500'); // Light red pulse
                recorderPulse.classList.remove('hidden');
                btnStop.classList.remove('hidden');
                btnPause.classList.remove('hidden');
                btnDiscard.classList.remove('hidden');
                recordStatus.textContent = "Grabando...";
                break;
            case 'paused':
                btnRecord.classList.add('opacity-50');
                btnRecord.disabled = true;
                btnStop.classList.remove('hidden');
                btnResume.classList.remove('hidden');
                btnDiscard.classList.remove('hidden');
                recordStatus.textContent = "Grabación en pausa";
                break;
            case 'ready':
                recordStatus.textContent = "Grabación lista";
                break;
        }
    };

    const startTimer = () => {
        if (recordTimerInterval) clearInterval(recordTimerInterval);
        recordingStartTime = Date.now();
        totalPausedTime = 0;
        
        recordTimerInterval = setInterval(() => {
            let now = Date.now();
            let elapsed;
            
            if (mediaRecorder && mediaRecorder.state === 'paused') {
                elapsed = (pausedStartTime - recordingStartTime - totalPausedTime) / 1000;
            } else {
                elapsed = (now - recordingStartTime - totalPausedTime) / 1000;
            }
            
            recordTimerText.textContent = formatTime(Math.max(0, elapsed));
        }, 200);
    };

    // --- Recording Logic ---
    btnRecord.addEventListener('click', async () => {
        recordedBlob = null;
        audioChunks = [];
        sttPlayerSection.classList.add('hidden');
        sttSizeWarning.classList.add('hidden');
        sttRecordSizeDisplay.classList.add('hidden');
        
        if (!navigator.mediaDevices || !window.MediaRecorder) {
            setSttStatus("Grabación no soportada. Usa Safari o sube un archivo.", "error");
            return;
        }

        const mimeType = getSupportedMimeType();
        if (!mimeType) {
            setSttStatus("Formato de grabación no soportado.", "error");
            return;
        }
        recordingMimeType = mimeType;

        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            mediaRecorder = new MediaRecorder(stream, { mimeType: recordingMimeType });
            
            mediaRecorder.ondataavailable = (event) => {
                if (event.data && event.data.size > 0) audioChunks.push(event.data);
            };

            mediaRecorder.onstop = () => {
                recordedBlob = new Blob(audioChunks, { type: recordingMimeType });
                const sizeMB = (recordedBlob.size / (1024 * 1024)).toFixed(2);
                
                sttRecordSizeDisplay.textContent = `${sizeMB} MB`;
                sttRecordSizeDisplay.classList.remove('hidden');

                if (recordedBlob.size === 0) {
                    setSttStatus("Grabación vacía. Intenta de nuevo.", "error");
                    recordedBlob = null;
                } else {
                    // Load into player
                    const url = URL.createObjectURL(recordedBlob);
                    sttAudio.src = url;
                    sttAudio.load();
                    sttPlayerSection.classList.remove('hidden');
                    
                    // 30MB Guard
                    if (recordedBlob.size > 30 * 1024 * 1024) {
                        sttSizeWarning.classList.remove('hidden');
                        btnTranscribe.disabled = true;
                    } else {
                        sttSelectedFile = null;
                        updateTranscribeButton();
                    }
                }
            };

            mediaRecorder.start(100);
            setRecorderUIState('recording');
            startTimer();

        } catch (err) {
            setSttStatus("Error de micrófono o permisos.", "error");
            console.error(err);
        }
    });

    btnPause.addEventListener('click', () => {
        if (mediaRecorder && mediaRecorder.state === 'recording') {
            mediaRecorder.pause();
            pausedStartTime = Date.now();
            setRecorderUIState('paused');
        }
    });

    btnResume.addEventListener('click', () => {
        if (mediaRecorder && mediaRecorder.state === 'paused') {
            totalPausedTime += (Date.now() - pausedStartTime);
            mediaRecorder.resume();
            setRecorderUIState('recording');
        }
    });

    const discardRecording = () => {
        if (mediaRecorder) {
            if (mediaRecorder.state !== 'inactive') mediaRecorder.stop();
            if (mediaRecorder.stream) {
                mediaRecorder.stream.getTracks().forEach(track => track.stop());
            }
        }
        clearInterval(recordTimerInterval);
        audioChunks = [];
        recordedBlob = null;
        sttAudio.src = '';
        sttPlayerSection.classList.add('hidden');
        sttRecordSizeDisplay.classList.add('hidden');
        sttSizeWarning.classList.add('hidden');
        setRecorderUIState('idle');
        updateTranscribeButton();
    };

    btnDiscard.addEventListener('click', discardRecording);

    btnStop.addEventListener('click', () => {
        if (mediaRecorder && mediaRecorder.state !== 'inactive') {
            mediaRecorder.stop();
            mediaRecorder.stream.getTracks().forEach(track => track.stop());
            clearInterval(recordTimerInterval);
            setRecorderUIState('ready');
        }
    });

    // Subida de archivo (Upload) logic
    sttDropzone.addEventListener('click', () => sttFile.click());
    
    sttFile.addEventListener('change', (e) => {
        const file = e.target.files[0];
        if (file) {
            sttSelectedFile = file;
            recordedBlob = null;
            sttPlayerSection.classList.add('hidden');
            sttRecordSizeDisplay.classList.add('hidden');
            sttSizeWarning.classList.add('hidden');
            
            sttFileFeedback.classList.remove('hidden');
            sttFileName.textContent = file.name;
            
            // File size validation (30MB)
            if (file.size > 30 * 1024 * 1024) {
                sttSizeWarning.classList.remove('hidden');
                btnTranscribe.disabled = true;
            } else {
                updateTranscribeButton();
            }
        }
    });

    btnRemoveSttFile.addEventListener('click', (e) => {
        e.stopPropagation();
        sttSelectedFile = null;
        sttFile.value = '';
        sttFileFeedback.classList.add('hidden');
        updateTranscribeButton();
    });

    const updateTranscribeButton = () => {
        if ((sttSelectedFile && sttSelectedFile.size <= 30 * 1024 * 1024) || 
            (recordedBlob && recordedBlob.size <= 30 * 1024 * 1024)) {
            btnTranscribe.disabled = false;
            btnTranscribe.classList.replace('bg-slate-200', 'bg-gradient-to-r');
            btnTranscribe.classList.add('from-blue-600', 'to-indigo-600', 'text-white');
            btnTranscribe.classList.remove('text-slate-400');
        } else {
            btnTranscribe.disabled = true;
            btnTranscribe.classList.replace('bg-gradient-to-r', 'bg-slate-200');
            btnTranscribe.classList.remove('from-blue-600', 'to-indigo-600', 'text-white');
            btnTranscribe.classList.add('text-slate-400');
        }
    };

    // --- STT Player Control Logic ---
    sttBtnPlayPause.addEventListener('click', () => {
        if (sttAudio.paused) sttAudio.play();
        else sttAudio.pause();
    });

    sttAudio.addEventListener('play', () => sttIconPlayPause.classList.replace('ph-play', 'ph-pause'));
    sttAudio.addEventListener('pause', () => sttIconPlayPause.classList.replace('ph-pause', 'ph-play'));
    sttAudio.addEventListener('ended', () => {
        sttIconPlayPause.classList.replace('ph-pause', 'ph-play');
        sttAudio.currentTime = 0;
    });

    sttAudio.addEventListener('loadedmetadata', () => sttTimeTotal.textContent = formatTime(sttAudio.duration));
    sttAudio.addEventListener('timeupdate', () => {
        if (!sttAudio.duration || isSttDragging) return;
        sttTimeCurrent.textContent = formatTime(sttAudio.currentTime);
        const progress = (sttAudio.currentTime / sttAudio.duration) * 100;
        sttProgressPlayed.style.width = `${progress}%`;
        sttProgressThumb.style.left = `${progress}%`;
    });

    sttBtnRewind.addEventListener('click', () => sttAudio.currentTime = Math.max(0, sttAudio.currentTime - 10));
    sttBtnForward.addEventListener('click', () => sttAudio.currentTime = Math.min(sttAudio.duration, sttAudio.currentTime + 10));

    // STT Timeline seek
    const updateSttSeek = (e) => {
        const rect = sttProgressContainer.getBoundingClientRect();
        const clientX = e.touches ? e.touches[0].clientX : e.clientX;
        const pos = Math.max(0, Math.min(clientX - rect.left, rect.width));
        const percentage = pos / rect.width;
        sttProgressPlayed.style.width = `${percentage * 100}%`;
        sttProgressThumb.style.left = `${percentage * 100}%`;
        return percentage;
    };

    sttProgressContainer.addEventListener('mousedown', (e) => { isSttDragging = true; updateSttSeek(e); });
    document.addEventListener('mousemove', (e) => { if (isSttDragging) updateSttSeek(e); });
    document.addEventListener('mouseup', (e) => { 
        if (isSttDragging) {
            isSttDragging = false;
            sttAudio.currentTime = updateSttSeek(e) * sttAudio.duration;
        }
    });

    // --- Local Download ---
    btnDownloadRecorded.addEventListener('click', () => {
        if (!recordedBlob) return;
        const ext = recordingMimeType.includes('mp4') ? 'mp4' : recordingMimeType.includes('aac') ? 'aac' : 'webm';
        const url = URL.createObjectURL(recordedBlob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `grabacion_${new Date().getTime()}.${ext}`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
    });

    // Trigger transcribir
    btnTranscribe.addEventListener('click', async () => {
        const formData = new FormData();
        const fileToUpload = recordedBlob || sttSelectedFile;
        if (!fileToUpload) return;
        
        // Final guard
        if (fileToUpload.size > 30 * 1024 * 1024) {
            setSttStatus("Archivo demasiado grande (> 30MB).", "error");
            return;
        }

        if (recordedBlob) {
            const ext = recordingMimeType.includes('mp4') ? 'mp4' : recordingMimeType.includes('aac') ? 'aac' : 'webm';
            formData.append('audio', recordedBlob, `recording.${ext}`);
        } else {
            formData.append('audio', sttSelectedFile);
        }

        btnTranscribe.disabled = true;
        transcribeText.textContent = "Transcribiendo con AI...";
        transcribeIcon.classList.add('hidden');
        transcribeSpinner.classList.remove('hidden');
        
        let statusMsg = "Procesando audio, por favor espera...";
        // If file > 15MB, it's likely over 5 mins
        if (fileToUpload.size > 15 * 1024 * 1024) {
            statusMsg = "Audio largo detectado. Se procesará por partes. Por favor, no cierres esta pestaña.";
        }
        setSttStatus(statusMsg, "info");
        sttResultArea.classList.add('hidden');

        try {
            const response = await fetch('/api/transcribe', {
                method: 'POST',
                headers: { 'X-CSRFToken': csrfToken },
                body: formData
            });

            if (response.status === 413) throw new Error("Archivo demasiado grande para el servidor (413).");
            
            const data = await response.json();
            if (!response.ok) throw new Error(data.error || "Error al transcribir.");

            sttOutput.value = data.text;
            sttCharCounter.textContent = `${data.text.length} caracteres`;
            sttResultArea.classList.remove('hidden');
            setSttStatus("Transcripción completada con éxito.", "success");
        } catch (err) {
            setSttStatus(err.message, "error");
        } finally {
            btnTranscribe.disabled = false;
            transcribeText.textContent = "Transcribir a Texto";
            transcribeSpinner.classList.add('hidden');
            transcribeIcon.classList.remove('hidden');
        }
    });

    // --- Result Actions ---
    btnCopyStt.addEventListener('click', () => {
        sttOutput.select();
        document.execCommand('copy');
        const originalText = btnCopyStt.innerHTML;
        btnCopyStt.innerHTML = '<i class="ph-fill ph-check"></i> ¡Copiado!';
        setTimeout(() => btnCopyStt.innerHTML = originalText, 2000);
    });

    btnDownloadStt.addEventListener('click', () => {
        const blob = new Blob([sttOutput.value], { type: 'text/plain' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `transcripcion_${new Date().getTime()}.txt`;
        a.click();
        URL.revokeObjectURL(url);
    });

    sttOutput.addEventListener('input', () => {
        sttCharCounter.textContent = `${sttOutput.value.length} caracteres`;
    });

});
