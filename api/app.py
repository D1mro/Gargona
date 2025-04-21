from __future__ import annotations
from flask import Flask, request, jsonify, render_template
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from openai import OpenAI
import os
from typing import List, Dict, Optional

app = Flask(__name__, static_folder='../static', template_folder='../templates')

# Конфигурация (рекомендуется использовать переменные окружения)
class Config:
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "your-api-key")
    FINE_TUNED_MODEL_ID = os.getenv("FINE_TUNED_MODEL_ID", "ft:gpt-4o-mini-2024-07-18:personal::BNkHOZVU")
    EMAIL_SETTINGS = {
        'smtp_server': os.getenv("SMTP_SERVER", "smtp.gmail.com"),
        'smtp_port': int(os.getenv("SMTP_PORT", 587)),
        'sender_email': os.getenv("SENDER_EMAIL", "your-email@gmail.com"),
        'sender_password': os.getenv("SENDER_PASSWORD", "your-password"),
        'recipient_email': os.getenv("RECIPIENT_EMAIL", "recipient@mail.ru")
    }
    MAX_HISTORY = 10

# Инициализация клиента OpenAI
client = OpenAI(api_key=Config.OPENAI_API_KEY)




# Системный промпт
SYSTEM_PROMPT = """Ты Гаргона, ИИ-консультант завода ROK по камнеобработке. Следуй правилам:

1. Тематика:
- Только натуральный камень: мрамор, гранит, оникс, травертин, кварцит
- Изделия: столешницы, подоконники, ступени, мозаика, фасады
- Технологии: резка, полировка, термообработка, браширование

2. Запрещено:
- Давать информацию о других материалах
- Называть точные цены (предлагай оставить заявку)
- Отвечать на вопросы не по тематике

3. Стиль:
- Профессионально, но дружелюбно
- Короткие сообщения (10-20 слов)
- 1 эмоджи в каждом 2-3 сообщении
- Уточняй детали при неполных данных"""

# Глобальные переменные
chat_history: List[Dict[str, str]] = []
client_phone: Optional[str] = None

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/start', methods=['POST'])
def start_chat():
    """Инициализация чата с приветственным сообщением"""
    welcome_msg = "Здравствуйте! Я Гаргона, консультант завода ROK. Помогу с выбором изделий из натурального камня. Чем вам помочь? ✨"
    chat_history.clear()
    chat_history.append({'role': 'assistant', 'content': welcome_msg})
    return jsonify({'text': welcome_msg})

@app.route('/chat', methods=['POST'])
def handle_message():
    """Обработка сообщений пользователя"""
    global chat_history
    
    user_input = request.form.get('message', '').strip()
    if not user_input:
        return jsonify({'error': 'Пустое сообщение'}), 400

    try:
        # Добавляем сообщение пользователя
        chat_history.append({'role': 'user', 'content': user_input})
        
        # Формируем контекст
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            *[{"role": msg['role'], "content": msg['content']} 
              for msg in chat_history[-Config.MAX_HISTORY:]]
        ]
        
        # Запрос к модели
        response = client.chat.completions.create(
            model=Config.FINE_TUNED_MODEL_ID,
            messages=messages,
            temperature=0.3,
            max_tokens=500,
            frequency_penalty=0.2
        )

        assistant_response = response.choices[0].message.content
        
        # Сохраняем ответ и возвращаем результат
        chat_history.append({'role': 'assistant', 'content': assistant_response})
        return jsonify({
            'text': assistant_response,
            'history': [msg for msg in chat_history if msg['role'] != 'system']
        })
        
    except Exception as e:
        app.logger.error(f"Ошибка OpenAI: {str(e)}")
        return jsonify({'error': 'Ошибка обработки запроса'}), 500

@app.route('/submit_contact', methods=['POST'])
def submit_contact():
    """Обработка контактных данных"""
    global client_phone
    
    name = request.form.get('name', '').strip()
    phone = request.form.get('phone', '').strip()
    
    if not name or not phone:
        return jsonify({'status': 'error', 'message': 'Заполните все поля'}), 400
    
    client_phone = phone
    
    try:
        # Формируем текст заявки
        conversation = "\n".join(
            f"{msg['role']}: {msg['content']}" 
            for msg in chat_history 
            if msg['role'] != 'system'
        )
        
        email_text = f"""Новая заявка от {name}
Телефон: {phone}

История переписки:
{conversation}"""
        
        # Отправка email
        if send_notification_email(email_text):
            return jsonify({
                'status': 'success',
                'message': 'Заявка отправлена! Менеджер свяжется с вами в ближайшее время.'
            })
        else:
            return jsonify({
                'status': 'warning',
                'message': 'Заявка принята, но не отправлена. Мы вам перезвоним.'
            })
            
    except Exception as e:
        app.logger.error(f"Ошибка обработки заявки: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': 'Ошибка обработки заявки'
        }), 500

def send_notification_email(text: str) -> bool:
    """Отправка уведомления на email"""
    try:
        msg = MIMEMultipart()
        msg['From'] = Config.EMAIL_SETTINGS['sender_email']
        msg['To'] = Config.EMAIL_SETTINGS['recipient_email']
        msg['Subject'] = 'Новая заявка с сайта ROK'
        msg.attach(MIMEText(text, 'plain', 'utf-8'))

        with smtplib.SMTP(
            Config.EMAIL_SETTINGS['smtp_server'], 
            Config.EMAIL_SETTINGS['smtp_port'],
            timeout=10
        ) as server:
            server.starttls()
            server.login(
                Config.EMAIL_SETTINGS['sender_email'],
                Config.EMAIL_SETTINGS['sender_password']
            )
            server.send_message(msg)
        
        return True
    except Exception as e:
        app.logger.error(f"Ошибка отправки email: {str(e)}")
        return False
    # Обработчик для Vercel
def handler(request):
    with app.app_context():
        response = app.full_dispatch_request()
        return response



if __name__ == '__main__':
    app.run()
