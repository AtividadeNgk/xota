import modules.manager as manager
import json
from datetime import datetime, timedelta

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CommandHandler, CallbackContext, CallbackQueryHandler, ContextTypes, ConversationHandler, MessageHandler, filters

from modules.utils import process_command, is_admin, cancel, error_callback, escape_markdown_v2

# Estados da conversa
RECUPERACAO_SELECIONAR, RECUPERACAO_ACAO, RECUPERACAO_MENSAGEM, RECUPERACAO_DESCONTO, RECUPERACAO_TEMPO_TIPO, RECUPERACAO_TEMPO_VALOR, RECUPERACAO_CONFIRMAR, RECUPERACAO_DELETAR = range(8)

keyboardc = [
    [InlineKeyboardButton("❌ CANCELAR", callback_data="cancelar")]
]
cancel_markup = InlineKeyboardMarkup(keyboardc)

async def recuperacao(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando principal de recuperação"""
    command_check = await process_command(update, context)
    if not command_check:
        return ConversationHandler.END
    
    if not await is_admin(context, update.message.from_user.id):
        return ConversationHandler.END
    
    context.user_data['conv_state'] = "recuperacao"
    
    # Busca recuperações existentes
    recovery_system = manager.get_bot_recovery_system(context.bot_data['id'])
    
    # Cria dicionário para mapear índices com recuperações existentes
    recovery_dict = {rec['index']: rec for rec in recovery_system}
    
    # Monta os botões das 5 recuperações
    keyboard = []
    for i in range(1, 6):
        button_text = f"{'✅ ' if i in recovery_dict else ''}RECUPERAÇÃO {i}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"rec_select_{i}")])
    
    keyboard.append([InlineKeyboardButton("❌ CANCELAR", callback_data="cancelar")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "🔄 Selecione qual recuperação deseja configurar:",
        reply_markup=reply_markup
    )
    return RECUPERACAO_SELECIONAR

async def recuperacao_selecionar(update: Update, context: CallbackContext):
    """Seleciona qual recuperação configurar"""
    query = update.callback_query
    await query.answer()
    
    if query.data == 'cancelar':
        await cancel(update, context)
        return ConversationHandler.END
    
    # Extrai o índice da recuperação
    rec_index = int(query.data.split('_')[-1])
    context.user_data['recovery_index'] = rec_index
    
    # Verifica se já existe
    recovery_system = manager.get_bot_recovery_system(context.bot_data['id'])
    existing = next((rec for rec in recovery_system if rec['index'] == rec_index), None)
    
    if existing:
        # Se existe, oferece opção de remover
        keyboard = [
            [InlineKeyboardButton("➖ REMOVER", callback_data="remover")],
            [InlineKeyboardButton("❌ CANCELAR", callback_data="cancelar")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Formata tempo para exibição
        time_display = f"{existing['time_value']} {existing['time_type']}"
        
        await query.message.edit_text(
            f"🔄 Recuperação {rec_index} já configurada:\n\n"
            f"💸 Desconto: {existing['discount']}%\n"
            f"⏱️ Tempo: {time_display}\n\n"
            f"Deseja remover esta recuperação?",
            reply_markup=reply_markup
        )
        return RECUPERACAO_ACAO
    else:
        # Se não existe, inicia configuração
        context.user_data['recovery_config'] = {
            'index': rec_index,
            'media': False,
            'text': False,
            'discount': 0,
            'time_type': '',
            'time_value': 0
        }
        
        await query.message.edit_text(
            f"🔄 Configurando Recuperação {rec_index}\n\n"
            f"📝 Envie o post (mídia + texto) para esta recuperação:",
            reply_markup=cancel_markup
        )
        return RECUPERACAO_MENSAGEM

async def recuperacao_acao(update: Update, context: CallbackContext):
    """Ação sobre recuperação existente"""
    query = update.callback_query
    await query.answer()
    
    if query.data == 'cancelar':
        await cancel(update, context)
        return ConversationHandler.END
    
    elif query.data == 'remover':
        rec_index = context.user_data['recovery_index']
        recovery_system = manager.get_bot_recovery_system(context.bot_data['id'])
        
        # Remove a recuperação
        recovery_system = [rec for rec in recovery_system if rec['index'] != rec_index]
        manager.update_bot_recovery_system(context.bot_data['id'], recovery_system)
        
        await query.message.edit_text(f"✅ Recuperação {rec_index} removida com sucesso!")
        context.user_data['conv_state'] = False
        return ConversationHandler.END

async def recuperacao_mensagem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recebe mensagem da recuperação"""
    try:
        save = {
            'media': False,
            'text': False
        }
        
        if update.message.photo:
            photo_file = await update.message.photo[-1].get_file()
            save['media'] = {
                'file': photo_file.file_id,
                'type': 'photo'
            }
        elif update.message.video:
            video_file = await update.message.video.get_file()
            save['media'] = {
                'file': video_file.file_id,
                'type': 'video'
            }
        elif update.message.text:
            save['text'] = update.message.text
        else:
            await update.message.reply_text("⛔ Somente texto ou mídia:", reply_markup=cancel_markup)
            return RECUPERACAO_MENSAGEM
        
        if update.message.caption:
            save['text'] = update.message.caption
        
        context.user_data['recovery_config']['media'] = save['media']
        context.user_data['recovery_config']['text'] = save['text']
        
        await update.message.reply_text(
            "💸 Quantos % de desconto deseja aplicar nesta recuperação?\n"
            "> Digite apenas o número (ex: 10 para 10%)",
            reply_markup=cancel_markup
        )
        return RECUPERACAO_DESCONTO
        
    except Exception as e:
        await update.message.reply_text(f"⛔ Erro ao salvar mensagem: {str(e)}")
        context.user_data['conv_state'] = False
        return ConversationHandler.END

async def recuperacao_desconto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recebe o desconto da recuperação"""
    if not update.message.text:
        await update.message.reply_text("⛔ Por favor, envie apenas o número:", reply_markup=cancel_markup)
        return RECUPERACAO_DESCONTO
    
    try:
        desconto = int(update.message.text)
        if desconto <= 0 or desconto >= 100:
            await update.message.reply_text(
                "⛔ O desconto deve estar entre 1% e 99%:",
                reply_markup=cancel_markup
            )
            return RECUPERACAO_DESCONTO
        
        context.user_data['recovery_config']['discount'] = desconto
        
        # Botões para tipo de tempo
        keyboard = [
            [
                InlineKeyboardButton("Segundos", callback_data="time_segundos"),
                InlineKeyboardButton("Minutos", callback_data="time_minutos")
            ],
            [
                InlineKeyboardButton("Horas", callback_data="time_horas"),
                InlineKeyboardButton("Dias", callback_data="time_dias")
            ],
            [InlineKeyboardButton("❌ CANCELAR", callback_data="cancelar")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "⏱️ Selecione a unidade de tempo:",
            reply_markup=reply_markup
        )
        return RECUPERACAO_TEMPO_TIPO
        
    except ValueError:
        await update.message.reply_text("⛔ Envie um número válido:", reply_markup=cancel_markup)
        return RECUPERACAO_DESCONTO

async def recuperacao_tempo_tipo(update: Update, context: CallbackContext):
    """Seleciona o tipo de tempo"""
    query = update.callback_query
    await query.answer()
    
    if query.data == 'cancelar':
        await cancel(update, context)
        return ConversationHandler.END
    
    time_type = query.data.split('_')[-1]
    context.user_data['recovery_config']['time_type'] = time_type
    
    await query.message.edit_text(
        f"⏱️ Quantos {time_type} após o /start?\n"
        f"> Digite apenas o número",
        reply_markup=cancel_markup
    )
    return RECUPERACAO_TEMPO_VALOR

async def recuperacao_tempo_valor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recebe o valor do tempo"""
    if not update.message.text:
        await update.message.reply_text("⛔ Por favor, envie apenas o número:", reply_markup=cancel_markup)
        return RECUPERACAO_TEMPO_VALOR
    
    try:
        tempo = int(update.message.text)
        if tempo <= 0:
            await update.message.reply_text("⛔ O tempo deve ser maior que zero:", reply_markup=cancel_markup)
            return RECUPERACAO_TEMPO_VALOR
        
        # Valida máximo de 7 dias
        time_type = context.user_data['recovery_config']['time_type']
        minutes_total = 0
        
        if time_type == 'segundos':
            minutes_total = tempo / 60
        elif time_type == 'minutos':
            minutes_total = tempo
        elif time_type == 'horas':
            minutes_total = tempo * 60
        elif time_type == 'dias':
            minutes_total = tempo * 24 * 60
        
        if minutes_total > 7 * 24 * 60:  # 7 dias em minutos
            await update.message.reply_text(
                "⛔ O tempo máximo é de 7 dias!",
                reply_markup=cancel_markup
            )
            return RECUPERACAO_TEMPO_VALOR
        
        context.user_data['recovery_config']['time_value'] = tempo
        
        # Monta mensagem de confirmação
        config = context.user_data['recovery_config']
        keyboard = [
            [InlineKeyboardButton("✅ CONFIRMAR", callback_data="confirmar")],
            [InlineKeyboardButton("❌ CANCELAR", callback_data="cancelar")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"🔄 Confirme a Recuperação {config['index']}:\n\n"
            f"💸 Desconto: {config['discount']}%\n"
            f"⏱️ Tempo: {tempo} {time_type} após o /start\n\n"
            f"Deseja criar esta recuperação?",
            reply_markup=reply_markup
        )
        return RECUPERACAO_CONFIRMAR
        
    except ValueError:
        await update.message.reply_text("⛔ Envie um número válido:", reply_markup=cancel_markup)
        return RECUPERACAO_TEMPO_VALOR

async def recuperacao_confirmar(update: Update, context: CallbackContext):
    """Confirma criação da recuperação"""
    query = update.callback_query
    await query.answer()
    
    if query.data == 'cancelar':
        await cancel(update, context)
        return ConversationHandler.END
    
    elif query.data == 'confirmar':
        try:
            # Busca recuperações existentes
            recovery_system = manager.get_bot_recovery_system(context.bot_data['id'])
            
            # Adiciona nova recuperação
            new_recovery = context.user_data['recovery_config']
            recovery_system.append(new_recovery)
            
            # Salva
            manager.update_bot_recovery_system(context.bot_data['id'], recovery_system)
            
            await query.message.edit_text(
                f"✅ Recuperação {new_recovery['index']} criada com sucesso!"
            )
            
        except Exception as e:
            await query.message.edit_text(f"⛔ Erro ao criar recuperação: {str(e)}")
        
        context.user_data['conv_state'] = False
        return ConversationHandler.END

# ConversationHandler
conv_handler_recuperacao = ConversationHandler(
    entry_points=[CommandHandler("recuperacao", recuperacao)],
    states={
        RECUPERACAO_SELECIONAR: [CallbackQueryHandler(recuperacao_selecionar)],
        RECUPERACAO_ACAO: [CallbackQueryHandler(recuperacao_acao)],
        RECUPERACAO_MENSAGEM: [MessageHandler(~filters.COMMAND, recuperacao_mensagem), CallbackQueryHandler(cancel)],
        RECUPERACAO_DESCONTO: [MessageHandler(~filters.COMMAND, recuperacao_desconto), CallbackQueryHandler(cancel)],
        RECUPERACAO_TEMPO_TIPO: [CallbackQueryHandler(recuperacao_tempo_tipo)],
        RECUPERACAO_TEMPO_VALOR: [MessageHandler(~filters.COMMAND, recuperacao_tempo_valor), CallbackQueryHandler(cancel)],
        RECUPERACAO_CONFIRMAR: [CallbackQueryHandler(recuperacao_confirmar)]
    },
    fallbacks=[CallbackQueryHandler(error_callback)]
)