import telebot
from telebot import types
import json
import os
from dotenv import load_dotenv
from flask import Flask
from threading import Thread

# Load secrets from .env file
load_dotenv()
API_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_ID = int(os.getenv('ADMIN_ID'))

CONFIG_FILE = 'bot_config.json'


def safe_format_message(template, **kwargs):
    """Safely formats a MarkdownV2 template and escapes all user-provided values."""
    # First, escape all replacement values for MarkdownV2
    escaped_kwargs = {}
    mdv2_reserved = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    
    for key, value in kwargs.items():
        text = str(value)
        for char in mdv2_reserved:
            text = text.replace(char, f'\\{char}')
        escaped_kwargs[key] = text
    
    # Format the template with escaped values
    return template.format(**escaped_kwargs)

# Default settings
DEFAULT_CONFIG = {
    "backup_group_id": -1004357266877,
    "main_group_id": -1003889685094,
    "backup_group_link": "https://t.me/+3tAJZ_vJdv42M2Nl",
    "main_group_link": "https://t.me/+WsDVzM3E6LUzNzU1",
    "welcome_msg": (
        "Welcome to National Media Share\\! 📁\n\n"
        "Here you can access, request, and share media by topic, as well as chat with fellow members\\.\n\n"
        "⚠️ *Please note the following rules\\:*\n\n"
        "\\- NSFW Channel: This is an 18\\+ NSFW community\\.\n"
        "\\- No Illegal Content: Any illegal contributions will result in an immediate and permanent ban\\.\n"
        "\\- No Spam: Self\\-promotion and catfishing are strictly prohibited\\.\n"
        "\\- Stay Active: You must contribute and participate regularly\\. Inactive members will be periodically removed\\."
    ),
    "success_msg": (
        "✅ *Verification Successful\\!*\\n\\n"
        "Welcome, {name}\\. You are now verified\\.\n\n"
        "Click below to enter the Main Group:"
    )
}


# Load or Create Config File
def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r' , encoding='utf-8') as f:
            loaded = json.load(f)
            # Ensure new keys exist even if the file is old
            if 'main_group_id' not in loaded:
                loaded['main_group_id'] = None
            return loaded
    else:
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG

def save_config(config):
    with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=4)

config = load_config()
bot = telebot.TeleBot(API_TOKEN)

admin_states = {} 

# --- HELPER FUNCTIONS ---

def is_admin(user_id):
    return user_id == ADMIN_ID

def get_cancel_markup():
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("❌ Cancel & Return to Menu", callback_data="admin_cancel"))
    return markup

def get_admin_menu():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("⚙️ View Settings", callback_data="admin_settings"),
        types.InlineKeyboardButton("🔢 Update Backup ID", callback_data="admin_set_id"),
        types.InlineKeyboardButton(" Update Main ID", callback_data="admin_set_main_id"),
        types.InlineKeyboardButton(" Update Backup Link", callback_data="admin_set_backup"),
        types.InlineKeyboardButton("🚀 Update Main Link", callback_data="admin_set_main"),
        types.InlineKeyboardButton("📝 Update Welcome Msg", callback_data="admin_set_welcome"),
        types.InlineKeyboardButton("✅ Update Success Msg", callback_data="admin_set_success")
    )
    return markup

# --- MAIN BOT LOGIC ---

@bot.message_handler(commands=['start', 'admin'])
def handle_start(message):
    user_id = message.from_user.id
    
    if is_admin(user_id):
        bot.send_message(message.chat.id, "🤖 **Admin Dashboard**\n\nSelect an option below to manage the bot:", reply_markup=get_admin_menu(), parse_mode='MarkdownV2')
        return

    user_name = message.from_user.first_name
    formatted_welcome = safe_format_message(config['welcome_msg'], name=user_name)
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton(" Join Backup Group", url=config['backup_group_link']),
        types.InlineKeyboardButton("✅ I have Joined the Backup", callback_data="check_backup_join")
    )
    
    bot.send_message(message.chat.id, formatted_welcome, reply_markup=markup, parse_mode='MarkdownV2')

# --- ADMIN BUTTON HANDLERS ---

@bot.callback_query_handler(func=lambda call: call.data.startswith('admin_'))
def admin_menu_handler(call):
    user_id = call.from_user.id
    
    if not is_admin(user_id):
        return bot.answer_callback_query(call.id, "🚫 Access Denied.", show_alert=True)

    action = call.data.replace('admin_', '')
    chat_id = call.message.chat.id
    msg_id = call.message.message_id
    
    # 1. CANCEL OPERATION
    if action == 'cancel':
        if user_id in admin_states:
            del admin_states[user_id]
        bot.edit_message_text("🤖 **Admin Dashboard**\n\nSelect an option below:", chat_id, msg_id, reply_markup=get_admin_menu(), parse_mode='MarkdownV2')
        return

    # 2. VIEW SETTINGS 
    if action == 'settings':
        def get_member_count(group_id):
            if not group_id: return "Not Set"
            try:
                chat_info = bot.get_chat(group_id)
                return str(chat_info.member_count)
            except Exception:
                # FIXED: Removed parentheses that were breaking MarkdownV2
                return "N/A \\- Add bot as Admin" 

        backup_members = get_member_count(config.get('backup_group_id'))
        main_members = get_member_count(config.get('main_group_id'))

        def escape_md(text):
            if not text: return ""
            # 1. Escape backslashes FIRST to prevent double-escaping issues
            text = text.replace('\\', '\\\\')
            # 2. Escape all other reserved MarkdownV2 characters
            for char in ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']:
                text = text.replace(char, f'\\{char}')
            return text

        def truncate(text, length=60):
            clean_text = text[:length].replace('\n', ' ') + "..." if len(text) > length else text
            return escape_md(clean_text)

        text = (
            "️ *Current Bot Settings & Stats:*\n\n"
            f"🔢 Backup Group ID: `{config.get('backup_group_id', 'Not Set')}`\n"
            f"👥 Backup Members: {backup_members}\n"
            f"🔗 Backup Link: {escape_md(str(config.get('backup_group_link', 'Not Set')))}\n\n"
            f" Main Group ID: `{config.get('main_group_id', 'Not Set')}`\n"
            f"👥 Main Members: {main_members}\n"
            f"🚀 Main Link: {escape_md(str(config.get('main_group_link', 'Not Set')))}\n\n"
            f"📝 Welcome Msg:\n{truncate(config.get('welcome_msg', ''))}\n\n"
            f"✅ Success Msg:\n{truncate(config.get('success_msg', ''))}"
        )
        
        back_markup = types.InlineKeyboardMarkup()
        back_markup.add(types.InlineKeyboardButton("🔙 Back to Menu", callback_data="admin_back"))
        bot.edit_message_text(text, chat_id, msg_id, reply_markup=back_markup, parse_mode='MarkdownV2') 
        
    elif action == 'back':
        bot.edit_message_text("🤖 **Admin Dashboard**\n\nSelect an option below:", chat_id, msg_id, reply_markup=get_admin_menu(), parse_mode='MarkdownV2')

    # 3. UPDATE SETTINGS
    elif action == 'set_id':
        admin_states[user_id] = 'waiting_for_id'
        # FIXED: Removed parentheses from prompt
        bot.edit_message_text(" **Update Backup Group ID**\n\nSend the new numeric ID e.g. -100123...:", chat_id, msg_id, reply_markup=get_cancel_markup())
        
    elif action == 'set_main_id':
        admin_states[user_id] = 'waiting_for_main_id'
        # FIXED: Removed parentheses from prompt
        bot.edit_message_text(" **Update Main Group ID**\n\nSend the new numeric ID e.g. -100123...:", chat_id, msg_id, reply_markup=get_cancel_markup())
        
    elif action == 'set_backup':
        admin_states[user_id] = 'waiting_for_backup_link'
        bot.edit_message_text(" **Update Backup Invite Link**\n\nSend the new invite link:", chat_id, msg_id, reply_markup=get_cancel_markup())
        
    elif action == 'set_main':
        admin_states[user_id] = 'waiting_for_main_link'
        bot.edit_message_text(" **Update Main Invite Link**\n\nSend the new invite link:", chat_id, msg_id, reply_markup=get_cancel_markup())
        
    elif action == 'set_welcome':
        admin_states[user_id] = 'waiting_for_welcome'
        bot.edit_message_text("📝 **Update Welcome Message**\n\nSend the new message.\n*Tip: use {name} for the user's first name*", chat_id, msg_id, reply_markup=get_cancel_markup())
        
    elif action == 'set_success':
        admin_states[user_id] = 'waiting_for_success'
        bot.edit_message_text("✅ **Update Success Message**\n\nSend the new message.\n*Tip: use {name} for the user's first name*", chat_id, msg_id, reply_markup=get_cancel_markup())
# --- HANDLE ADMIN TEXT INPUTS ---

@bot.message_handler(func=lambda message: message.from_user.id in admin_states)
def handle_admin_input(message):
    user_id = message.from_user.id
    state = admin_states[user_id]
    chat_id = message.chat.id
    
    try:
        if state == 'waiting_for_id':
            config['backup_group_id'] = int(message.text)
            bot.reply_to(message, f"✅ Backup ID updated to `{config['backup_group_id']}`", parse_mode='MarkdownV2')
            
        elif state == 'waiting_for_main_id':
            config['main_group_id'] = int(message.text)
            bot.reply_to(message, f"✅ Main Group ID updated to `{config['main_group_id']}`", parse_mode='MarkdownV2')
            
        elif state == 'waiting_for_backup_link':
            config['backup_group_link'] = message.text
            bot.reply_to(message, "✅ Backup Link updated\\!")
            
        elif state == 'waiting_for_main_link':
            config['main_group_link'] = message.text
            bot.reply_to(message, "✅ Main Link updated\\!")
            
        elif state == 'waiting_for_welcome':
            config['welcome_msg'] = message.text
            bot.reply_to(message, "✅ Welcome Message updated\\!")
            
        elif state == 'waiting_for_success':
            config['success_msg'] = message.text
            bot.reply_to(message, "✅ Success Message updated\\!")
   
        save_config(config)
        del admin_states[user_id]
        
        bot.send_message(chat_id, "🤖 **Admin Dashboard**\n\nSelect an option below:", reply_markup=get_admin_menu(), parse_mode='MarkdownV2')
        
    except ValueError:
        bot.reply_to(message, "❌ Invalid input. Please send a valid number or use the Cancel button.")
        del admin_states[user_id]

# --- USER VERIFICATION LOGIC ---

@bot.callback_query_handler(func=lambda call: call.data == "check_backup_join")
def check_membership(call):
    user_id = call.from_user.id
    user_name = call.from_user.first_name
    
    try:
        member_status = bot.get_chat_member(config['backup_group_id'], user_id)
        
        if member_status.status in ['member', 'administrator', 'creator']:
            success_markup = types.InlineKeyboardMarkup()
            success_markup.add(
                types.InlineKeyboardButton("🚀 Join Main Group", url=config['main_group_link'])
            )
            
            formatted_success = safe_format_message(config['success_msg'], name=user_name)
            
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=formatted_success,
                reply_markup=success_markup,
                parse_mode='MarkdownV2'
            )
            bot.answer_callback_query(call.id, "Verified\\!")
        else:
            bot.answer_callback_query(call.id, "❌ You haven't joined the backup group yet\\!", show_alert=True)
            
    except Exception as e:
        bot.answer_callback_query(call.id, "⚠️ Error verifying. Contact Admin.", show_alert=True)
        print(f"Error details: {e}")

print("Bot is running...")
# --- KEEP ALIVE & HEALTH MONITOR SETUP ---
app = Flask('')

@app.route('/')
def home():
    return "Bot is running and healthy!"

def run_server():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    server = Thread(target=run_server)
    server.daemon = True
    server.start()

if __name__ == "__main__":
    keep_alive() # Starts the web server in the background
    print("Bot is running...")
    bot.polling(none_stop=True, timeout=60) # timeout=60 prevents API spam