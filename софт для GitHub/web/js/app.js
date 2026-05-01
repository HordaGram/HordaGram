document.addEventListener("DOMContentLoaded", () => {
    const twaView = document.getElementById('twa-view');
    const browserView = document.getElementById('browser-view');
    
    const urlParams = new URLSearchParams(window.location.search);
    const archiveId = urlParams.get('archive');
    const isTelegramApp = Boolean(window.Telegram && window.Telegram.WebApp && window.Telegram.WebApp.initData);

    if (archiveId) {
        // Если архив, логику подхватит archive.js
        return;
    } 
    
    if (isTelegramApp) {
        // ==== TWA DASHBOARD ====
        twaView.style.display = 'flex'; 
        
        const tg = window.Telegram.WebApp;
        tg.expand();
        tg.ready();
        tg.setHeaderColor('#040b06');
        tg.setBackgroundColor('#040b06');

        const user = tg.initDataUnsafe?.user || { id: 123456789, first_name: "Аноним" };
        document.getElementById('user-name').textContent = user.first_name;

        async function fetchUserData() {
            try {
                const response = await fetch(`https://hordagram.duckdns.org/api/user/${user.id}`);
                const data = await response.json();
                
                document.querySelectorAll('.skeleton').forEach(el => el.classList.remove('skeleton'));

                if (data.error === "not_found") {
                    // ИСПРАВЛЕНИЕ БАГА ПУСТОЙ БАЗЫ
                    document.getElementById('status-text').textContent = 'Ожидание логов...';
                    document.getElementById('status-indicator').className = 'status-dot dot-red';
                    document.querySelector('[data-target="total-logs"]').textContent = "0";
                    document.querySelector('[data-target="today-logs"]').textContent = "0";
                    document.querySelector('[data-target="media-files"]').textContent = "0";
                    return;
                }

                if (data.status === 'alive') {
                    document.getElementById('status-indicator').className = 'status-dot dot-green';
                    document.getElementById('status-text').textContent = '🟢 Защита активна';
                } else {
                    document.getElementById('status-indicator').className = 'status-dot dot-red';
                    document.getElementById('status-text').textContent = '🔴 Сессия мертва';
                }

                document.querySelector('[data-target="total-logs"]').textContent = data.total_logs.toLocaleString('ru-RU');
                document.querySelector('[data-target="today-logs"]').textContent = data.today_logs.toLocaleString('ru-RU');
                document.querySelector('[data-target="media-files"]').textContent = data.media_files.toLocaleString('ru-RU');
            } catch (error) {
                console.error(error);
            }
        }

        fetchUserData();
        setInterval(fetchUserData, 5000);

    } else {
        // ==== БРАУЗЕР (ЛЕНДИНГ) ====
        browserView.style.display = 'flex';
        
        // Загружаем глобальную статистику
        fetch(`https://hordagram.duckdns.org/api/global_stats`)
            .then(res => res.json())
            .then(data => {
                // Плавное начисление цифр (анимация)
                let u = 0, l = 0;
                const interval = setInterval(() => {
                    u += Math.ceil(data.users / 50);
                    l += Math.ceil(data.logs / 50);
                    if (u >= data.users) { u = data.users; clearInterval(interval); }
                    if (l >= data.logs) l = data.logs;
                    document.getElementById('g-users').textContent = u.toLocaleString('ru-RU');
                    document.getElementById('g-logs').textContent = l.toLocaleString('ru-RU');
                }, 30);
            })
            .catch(e => console.log(e));
    }
});