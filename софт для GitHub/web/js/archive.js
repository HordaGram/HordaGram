document.addEventListener("DOMContentLoaded", () => {
    const archiveView = document.getElementById('archive-view');
    const urlParams = new URLSearchParams(window.location.search);
    const CURRENT_ARCHIVE_ID = urlParams.get('archive');
    const isTelegramApp = Boolean(window.Telegram && window.Telegram.WebApp && window.Telegram.WebApp.initData);

    if (!CURRENT_ARCHIVE_ID) return;

    // Включаем интерфейс архива
    archiveView.style.display = 'block';
    if (isTelegramApp) {
        window.Telegram.WebApp.expand();
        window.Telegram.WebApp.setHeaderColor('#040b06');
    }

    const chatBox = document.getElementById('chat-box');
    const mediaBox = document.getElementById('media-box');
    const searchInput = document.getElementById('search-input');
    
    // Вкладки
    document.getElementById('tab-chat').onclick = () => {
        document.getElementById('tab-chat').classList.add('active');
        document.getElementById('tab-media').classList.remove('active');
        chatBox.style.display = 'flex';
        mediaBox.style.display = 'none';
        document.getElementById('search-bar-container').style.display = 'none';
    };

    document.getElementById('tab-media').onclick = () => {
        document.getElementById('tab-media').classList.add('active');
        document.getElementById('tab-chat').classList.remove('active');
        chatBox.style.display = 'none';
        mediaBox.style.display = 'grid';
        document.getElementById('search-bar-container').style.display = 'none';
    };

    // Поиск
    document.getElementById('btn-search').onclick = () => {
        const bar = document.getElementById('search-bar-container');
        bar.style.display = bar.style.display === 'block' ? 'none' : 'block';
    };

    searchInput.addEventListener('input', (e) => {
        const val = e.target.value.toLowerCase();
        document.querySelectorAll('.msg-row').forEach(row => {
            if(row.innerText.toLowerCase().includes(val)) row.style.display = 'flex';
            else row.style.display = 'none';
        });
    });

    // Скачивание txt
    document.getElementById('btn-download').onclick = () => {
        window.location.href = `https://hordagram.duckdns.org/api/archive/${CURRENT_ARCHIVE_ID}/download`;
    };

    // Функция создания кастомного аудиоплеера
    function createCustomAudioPlayer(mediaUrl) {
        return `
            <div class="voice-player">
                <button class="play-btn" onclick="toggleAudio(this, '${mediaUrl}')"><i class="fa-solid fa-play"></i></button>
                <div class="progress-container" onclick="seekAudio(event, this)">
                    <div class="progress-bar"></div>
                </div>
            </div>
            <audio src="${mediaUrl}" style="display:none;" ontimeupdate="updateProgress(this)" onended="resetPlayer(this)"></audio>
        `;
    }

    async function loadArchiveData() {
        try {
            const response = await fetch(`https://hordagram.duckdns.org/api/archive/${CURRENT_ARCHIVE_ID}`);
            if (!response.ok) throw new Error("Архив был удален или не найден");
            const data = await response.json();
            
            document.getElementById('arch-title').textContent = data.chat_name;
            document.getElementById('arch-sub').textContent = `${data.messages.length} сообщений`;
            
            chatBox.innerHTML = ''; 
            mediaBox.innerHTML = '';
            
            data.messages.forEach(msg => {
                const isOut = (msg.sender_id === data.user_id);
                const row = document.createElement('div');
                row.className = `msg-row ${isOut ? 'out' : 'in'}`;
                
                const timeString = new Date(msg.timestamp + "Z").toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
                let contentHTML = `<div class="message-bubble">`;
                
                if (!isOut) contentHTML += `<div class="msg-author">${msg.sender_name}</div>`;
                
                // Медиа
                if (msg.media_dump_id && msg.media_dump_id > 0 && msg.msg_type !== 'text') {
                    const mediaUrl = `https://hordagram.duckdns.org/api/media/${data.user_id}/${msg.media_dump_id}`;
                    
                    if (msg.msg_type === 'photo') {
                        contentHTML += `<div class="msg-media" style="max-width: 250px;"><img src="${mediaUrl}"></div>`;
                        mediaBox.innerHTML += `<div class="grid-item"><img src="${mediaUrl}"></div>`;
                    } else if (msg.msg_type === 'video' || msg.msg_type === 'animation') {
                        contentHTML += `<div class="msg-media" style="max-width: 250px;"><video src="${mediaUrl}" controls></video></div>`;
                        mediaBox.innerHTML += `<div class="grid-item"><video src="${mediaUrl}"></video></div>`;
                    } else if (msg.msg_type === 'voice') {
                        contentHTML += createCustomAudioPlayer(mediaUrl);
                    } else if (msg.msg_type === 'video_note') {
                        contentHTML += `<div class="msg-media" style="text-align: center; background: transparent;">
                            <video style="width: 150px; height: 150px; border-radius: 50%; object-fit: cover; border: 2px solid var(--neon-light);" src="${mediaUrl}" autoplay loop muted onclick="this.muted = !this.muted"></video>
                        </div>`;
                    }
                }

                if (msg.text && msg.text !== "<i>Без текста</i>") contentHTML += `<div class="msg-text">${msg.text}</div>`;
                contentHTML += `<div class="msg-meta">${timeString}</div></div>`;
                
                row.innerHTML = contentHTML;
                chatBox.appendChild(row);
            });

            document.getElementById('island').style.display = 'flex';
            window.scrollTo(0, document.body.scrollHeight);

        } catch (e) {
            chatBox.innerHTML = `<div class="loading-text" style="color: var(--neon-alert);"><i class="fa-solid fa-triangle-exclamation"></i> ${e.message}</div>`;
        }
    }

    loadArchiveData();
});

// Глобальные функции плеера
window.toggleAudio = function(btn, url) {
    const container = btn.closest('.voice-player');
    const audio = container.nextElementSibling;
    const icon = btn.querySelector('i');
    
    // Останавливаем все остальные аудио
    document.querySelectorAll('audio').forEach(a => { if(a !== audio) { a.pause(); a.previousElementSibling.querySelector('.play-btn i').className = 'fa-solid fa-play'; }});

    if (audio.paused) {
        audio.play();
        icon.className = 'fa-solid fa-pause';
    } else {
        audio.pause();
        icon.className = 'fa-solid fa-play';
    }
};

window.updateProgress = function(audio) {
    const container = audio.previousElementSibling;
    const bar = container.querySelector('.progress-bar');
    const percentage = (audio.currentTime / audio.duration) * 100;
    bar.style.width = percentage + '%';
};

window.seekAudio = function(event, container) {
    const audio = container.parentElement.nextElementSibling;
    const rect = container.getBoundingClientRect();
    const pos = (event.clientX - rect.left) / rect.width;
    audio.currentTime = pos * audio.duration;
};

window.resetPlayer = function(audio) {
    const container = audio.previousElementSibling;
    const icon = container.querySelector('.play-btn i');
    const bar = container.querySelector('.progress-bar');
    icon.className = 'fa-solid fa-play';
    bar.style.width = '0%';
};

window.deleteArchive = async function() {
    const urlParams = new URLSearchParams(window.location.search);
    const id = urlParams.get('archive');
    if(!confirm("Удалить этот архив навсегда?")) return;
    try {
        await fetch(`https://hordagram.duckdns.org/api/archive/${id}`, { method: 'DELETE' });
        window.location.href = '/'; 
    } catch (e) {
        alert("Ошибка удаления!");
    }
};