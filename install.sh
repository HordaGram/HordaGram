#!/bin/bash

# Цвета для красивого вывода
GREEN="\033[1;32m"
CYAN="\033[1;36m"
RED="\033[1;31m"
YELLOW="\033[1;33m"
RESET="\033[0m"

clear
echo -e "${CYAN}=======================================${RESET}"
echo -e "${GREEN}       HordaGram VPS Installer         ${RESET}"
echo -e "${CYAN}=======================================${RESET}"
echo ""

# Выбор языка
echo "Select language / Выберите язык:"
echo "1) English"
echo "2) Русский"
read -p "-> " LANG_CHOICE

if [ "$LANG_CHOICE" == "2" ]; then
    MSG_KEY="Введите ваш ключ HordaKey:"
    MSG_CHECKING="Проверка ключа..."
    MSG_INVALID="Неверный ключ или он уже использован!"
    MSG_INSTALLING="Установка зависимостей..."
    MSG_DONE="Установка успешно завершена!"
    MSG_CREDS="Ваши данные для входа в бота:"
else
    MSG_KEY="Enter your HordaKey:"
    MSG_CHECKING="Checking key..."
    MSG_INVALID="Invalid key or already in use!"
    MSG_INSTALLING="Installing dependencies..."
    MSG_DONE="Installation completed successfully!"
    MSG_CREDS="Your login credentials for the bot:"
fi

# Запрос ключа
echo -e "\n${YELLOW}$MSG_KEY${RESET}"
read HORDA_KEY

echo -e "\n${CYAN}$MSG_CHECKING${RESET}"

# Получаем IP сервера
SERVER_IP=$(curl -s ifconfig.me)

# API-запрос к твоему центральному серверу (Укажешь тут свой домен)
# Сервер должен ответить JSON'ом: {"status": "ok"} или {"status": "error"}
RESPONSE=$(curl -s -X POST https://api.tvoy-domen.ru/verify-key \
    -H "Content-Type: application/json" \
    -d "{\"key\": \"$HORDA_KEY\", \"ip\": \"$SERVER_IP\"}")

STATUS=$(echo $RESPONSE | grep -o '"status":"ok"')

if [ -z "$STATUS" ]; then
    echo -e "${RED}$MSG_INVALID${RESET}"
    exit 1
fi

echo -e "${GREEN}Key is Valid! Proceeding...${RESET}"
echo -e "${CYAN}$MSG_INSTALLING${RESET}"

# Установка Python и зависимостей
sudo apt update -y > /dev/null 2>&1
sudo apt install python3 python3-pip python3-venv git jq -y > /dev/null 2>&1

# Клонируем репозиторий (замени на свою ссылку)
cd /opt
sudo rm -rf HordaGram-Node
sudo git clone https://github.com/ТВОЙ_ЮЗЕР/HordaGram-Node.git > /dev/null 2>&1
cd HordaGram-Node

# Создаем виртуальное окружение
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt > /dev/null 2>&1

# Генерация Логина и Пароля
LOGIN=$(head -c 4 /dev/urandom | hex)
PASSWORD=$(head -c 8 /dev/urandom | hex)

# Сохраняем настройки в .env
cat <<EOF > .env
VPS_LOGIN=$LOGIN
VPS_PASSWORD=$PASSWORD
HORDA_KEY=$HORDA_KEY
EOF

# Создаем systemd сервис
cat <<EOF | sudo tee /etc/systemd/system/hordagram.service
[Unit]
Description=HordaGram VPS Node
After=network.target

[Service]
User=root
WorkingDirectory=/opt/HordaGram-Node
ExecStart=/opt/HordaGram-Node/venv/bin/python vps_api.py
Restart=always

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable hordagram
sudo systemctl start hordagram

clear
echo -e "${CYAN}=======================================${RESET}"
echo -e "${GREEN}$MSG_DONE${RESET}"
echo -e "${CYAN}=======================================${RESET}"
echo -e "${YELLOW}$MSG_CREDS${RESET}"
echo ""
echo -e "IP Address : ${GREEN}$SERVER_IP${RESET}"
echo -e "Login      : ${GREEN}$LOGIN${RESET}"
echo -e "Password   : ${GREEN}$PASSWORD${RESET}"
echo ""
echo -e "Теперь перейдите в нашего бота и нажмите 'Управление', чтобы ввести эти данные."
echo -e "${CYAN}=======================================${RESET}"