import modules.manager as manager
import json, re, requests
import asyncio
from datetime import datetime, timedelta

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, CallbackContext, CallbackQueryHandler, ContextTypes, ConversationHandler, MessageHandler, filters, Updater, CallbackContext, ChatJoinRequestHandler
from telegram.error import BadRequest, Conflict

from modules.utils import process_command, is_admin, cancel, error_callback, error_message, escape_markdown_v2


def add_user_to_list(user, bot_id):
    print(user)
    print(bot_id)
    users = manager.get_bot_users(bot_id)
    print(users)
    if not user in users:
        users.append(user)
        manager.update_bot_users(bot_id, users)

def schedule_recovery_tasks(user_id, bot_id):
    """Agenda todas as tarefas de recuperação para um usuário"""
    # Busca o sistema de recuperação
    recovery_system = manager.get_bot_recovery_system(bot_id)
    
    if not recovery_system:
        return
    
    # Cancela tarefas anteriores deste usuário
    manager.cancel_user_recovery_tasks(user_id, bot_id)
    
    # Cria novas tarefas
    for recovery in recovery_system:
        # Calcula tempo de disparo
        scheduled_time = datetime.now()
        
        if recovery['time_type'] == 'segundos':
            scheduled_time += timedelta(seconds=recovery['time_value'])
        elif recovery['time_type'] == 'minutos':
            scheduled_time += timedelta(minutes=recovery['time_value'])
        elif recovery['time_type'] == 'horas':
            scheduled_time += timedelta(hours=recovery['time_value'])
        elif recovery['time_type'] == 'dias':
            scheduled_time += timedelta(days=recovery['time_value'])
        
        # Cria a tarefa
        manager.create_recovery_task(
            user_id=user_id,
            bot_id=bot_id,
            recovery_index=recovery['index'],
            scheduled_time=scheduled_time.strftime('%Y-%m-%d %H:%M:%S')
        )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    config = manager.get_bot_config(context.bot_data['id'])
    user_id = str(update.message.from_user.id)
    bot_id = context.bot_data['id']
    
    add_user_to_list(user_id, bot_id)
    
    # Agenda as recuperações
    schedule_recovery_tasks(user_id, bot_id)
    
    print(config)

    keyboard = [
        [InlineKeyboardButton(config['button'], callback_data='acessar_ofertas')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if config.get('midia', False):
        if config['midia'].get('type') == 'photo':
            await context.bot.send_photo(chat_id=user_id, photo=config['midia']['file'])
        else:
            await context.bot.send_video(chat_id=user_id, video=config['midia']['file'])

    if config.get('texto1', False):
        await context.bot.send_message(chat_id=user_id, text=config['texto1'])

    await context.bot.send_message(chat_id=user_id, text=config['texto2'], reply_markup=reply_markup)
    return ConversationHandler.END