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
    const btnPlayRecorded = document.getElementById('btn-play-recorded');
    const recorderPulse = document.getElementById('recorder-pulse');
    const recordStatus = document.getElementById('record-status');
    const recordTimerText = document.getElementById('record-timer');
    
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
    let recordedBlob = null;
    let sttSelectedFile = null;
    let recordingMimeType = 'audio/webm'; // Default

    // Helper to find supported MIME type (Crucial for iOS)
    const getSupportedMimeType = () => {
        const types = [
            'audio/webm;codecs=opus',
            'audio/webm',
            'audio/mp4',
            'audio/aac',
            'audio/ogg;codecs=opus'
        ];
        for (const type of types) {
            if (MediaRecorder.isTypeSupported(type)) {
                console.log(`MIME Type supported: ${type}`);
                return type;
            }
        }
        return '';
    };

    // Helper for STT status
    const setSttStatus = (msg, type = 'info') => {
        sttStatus.textContent = msg;
        sttStatus.classList.remove('hidden', 'bg-red-50', 'text-red-600', 'bg-blue-50', 'text-blue-600', 'bg-green-50', 'text-green-600');
        if (type === 'error') sttStatus.classList.add('bg-red-50', 'text-red-600');
        else if (type === 'success') sttStatus.classList.add('bg-green-50', 'text-green-700');
        else sttStatus.classList.add('bg-blue-50', 'text-blue-600');
    };

    // --- Recording Logic ---
    btnRecord.addEventListener('click', async () => {
        // Clear previous recording data
        recordedBlob = null;
        audioChunks = [];
        
        // Check Browser Support
        if (!navigator.mediaDevices || !window.MediaRecorder) {
            setSttStatus("La grabación no está soportada en este navegador. Usa Safari o sube un archivo.", "error");
            return;
        }

        const mimeType = getSupportedMimeType();
        if (!mimeType) {
            setSttStatus("No se encontró ningún formato de grabación soportado en este navegador.", "error");
            return;
        }
        recordingMimeType = mimeType;

        try {
            console.log("Requesting microphone permissions...");
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            console.log("Permissions granted. Initializing MediaRecorder...");
            
            mediaRecorder = new MediaRecorder(stream, { mimeType: recordingMimeType });
            
            mediaRecorder.ondataavailable = (event) => {
                if (event.data && event.data.size > 0) {
                    audioChunks.push(event.data);
                    console.log(`Data available: ${event.data.size} bytes`);
                }
            };

            mediaRecorder.onstop = () => {
                console.log("MediaRecorder stopped.");
                recordedBlob = new Blob(audioChunks, { type: recordingMimeType });
                console.log(`Blob created: ${recordedBlob.size} bytes (${recordedBlob.type})`);
                
                if (recordedBlob.size === 0) {
                    setSttStatus("La grabación generó un archivo vacío. Intenta de nuevo o usa otro navegador.", "error");
                    recordedBlob = null;
                } else {
                    btnPlayRecorded.classList.remove('hidden');
                    sttSelectedFile = null; // Prioritize recording
                }
                updateTranscribeButton();
            };

            mediaRecorder.onerror = (e) => {
                console.error("MediaRecorder error:", e);
                setSttStatus("Error durante la grabación. Inténtalo de nuevo.", "error");
            };

            mediaRecorder.start(100); // Collect data every 100ms
            console.log("MediaRecorder started.");
            
            // UI Update
            btnRecord.classList.add('animate-pulse', 'bg-red-500', 'text-white');
            recorderPulse.classList.remove('hidden');
            btnStop.classList.remove('hidden');
            btnPlayRecorded.classList.add('hidden');
            recordStatus.textContent = "Grabando...";
            
            // Timer logic
            let seconds = 0;
            if (recordTimerInterval) clearInterval(recordTimerInterval);
            recordTimerInterval = setInterval(() => {
                seconds++;
                const m = Math.floor(seconds / 60).toString().padStart(2, '0');
                const s = (seconds % 60).toString().padStart(2, '0');
                recordTimerText.textContent = `${m}:${s}`;
            }, 1000);

        } catch (err) {
            console.error("Error accessing microphone or initializing recorder:", err);
            if (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError') {
                setSttStatus("Permiso de micrófono denegado. Actívalo en los ajustes de tu navegador.", "error");
            } else {
                setSttStatus(`Error: ${err.message}`, "error");
            }
        }
    });

    btnStop.addEventListener('click', () => {
        if (mediaRecorder && mediaRecorder.state !== 'inactive') {
            mediaRecorder.stop();
            mediaRecorder.stream.getTracks().forEach(track => track.stop());
            
            clearInterval(recordTimerInterval);
            btnRecord.classList.remove('animate-pulse', 'bg-red-500', 'text-white');
            recorderPulse.classList.add('hidden');
            btnStop.classList.add('hidden');
            recordStatus.textContent = "Grabación lista";
        }
    });

    btnPlayRecorded.addEventListener('click', () => {
        if (recordedBlob) {
            const url = URL.createObjectURL(recordedBlob);
            const tempAudio = new Audio(url);
            tempAudio.play();
        }
    });

    // --- Upload Logic ---
    sttDropzone.addEventListener('click', () => sttFile.click());
    
    sttFile.addEventListener('change', (e) => {
        const file = e.target.files[0];
        if (file) {
            sttSelectedFile = file;
            recordedBlob = null; // Clear recording if file is selected
            sttFileFeedback.classList.remove('hidden');
            sttFileName.textContent = file.name;
            updateTranscribeButton();
            recordStatus.textContent = "Grabar nota de voz"; // Reset recorder text
            btnPlayRecorded.classList.add('hidden');
            if (recordTimerInterval) {
                clearInterval(recordTimerInterval);
                recordTimerText.textContent = "00:00";
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
        if (sttSelectedFile || recordedBlob) {
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

    // --- Transcription Workflow ---
    btnTranscribe.addEventListener('click', async () => {
        const payload = new FormData();
        if (recordedBlob) {
            const extension = recordingMimeType.includes('mp4') ? 'mp4' : 
                             recordingMimeType.includes('aac') ? 'aac' : 'webm';
            payload.append('audio', recordedBlob, `recording.${extension}`);
        } else if (sttSelectedFile) {
            payload.append('audio', sttSelectedFile);
        } else {
            return;
        }

        // Set Loading State
        btnTranscribe.disabled = true;
        transcribeText.textContent = "Transcribiendo con AI...";
        transcribeIcon.classList.add('hidden');
        transcribeSpinner.classList.remove('hidden');
        setSttStatus("Procesando audio, por favor espera...", "info");
        sttResultArea.classList.add('hidden');

        try {
            console.log("Starting transcription request...");
            const response = await fetch('/api/transcribe', {
                method: 'POST',
                headers: {
                    'X-CSRFToken': csrfToken
                },
                body: payload
            });

            const data = await response.json();
            if (!response.ok) throw new Error(data.error || "Error al transcribir.");

            // Success
            console.log("Transcription successful.");
            sttOutput.value = data.text;
            sttCharCounter.textContent = `${data.text.length} caracteres`;
            sttResultArea.classList.remove('hidden');
            setSttStatus("Transcripción completada con éxito.", "success");

        } catch (err) {
            console.error("Transcription error:", err);
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
