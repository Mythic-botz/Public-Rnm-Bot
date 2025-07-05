import os
import re
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ChatAction
import logging
from threading import Thread
from http.server import HTTPServer, BaseHTTPRequestHandler

# Enable logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

class AnimeRenameBot:
    def __init__(self, token):
        self.token = token
        self.app = Application.builder().token(token).build()
        self.setup_handlers()
    
    def setup_handlers(self):
        """Setup bot command and message handlers"""
        self.app.add_handler(CommandHandler("start", self.start))
        self.app.add_handler(CommandHandler("help", self.help_command))
        self.app.add_handler(MessageHandler(filters.Document.ALL, self.handle_document))
        self.app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text))
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Send a message when the command /start is issued"""
        welcome_text = """
🎌 **Anime Auto Rename Bot** 🎌

Welcome! I can help you automatically rename anime files with proper formatting.

**Features:**
• Auto-detect anime names from filenames
• Standardize episode numbering
• Clean up messy filenames
• Support for various anime file formats

Send me an anime file and I'll rename it for you!

Use /help for more information.
        """
        await update.message.reply_text(welcome_text, parse_mode='Markdown')
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Send help information"""
        help_text = """
🔧 **How to use:**

1. Send me an anime video file
2. I'll automatically detect the anime name and episode
3. You'll receive the renamed file

**Supported formats:**
• .mkv, .mp4, .avi, .mov, .wmv

**Naming patterns I can detect:**
• `[SubGroup] Anime Name - 01 [Quality].mkv`
• `Anime.Name.S01E01.mkv`
• `Anime Name Episode 01.mp4`
• And many more!

**Commands:**
/start - Start the bot
/help - Show this help message

**Note:** Large files may take some time to process.
        """
        await update.message.reply_text(help_text, parse_mode='Markdown')
    
    def extract_anime_info(self, filename):
        """Extract anime name and episode from filename"""
        # Remove file extension
        name = os.path.splitext(filename)[0]
        
        # Common anime filename patterns
        patterns = [
            # [SubGroup] Anime Name - 01 [Quality]
            r'\[.*?\]\s*(.+?)\s*-\s*(\d+)',
            # Anime.Name.S01E01 or Anime.Name.Episode.01
            r'(.+?)\.(?:S\d+E(\d+)|Episode\.(\d+))',
            # Anime Name Episode 01
            r'(.+?)\s+Episode\s+(\d+)',
            # Anime Name - 01
            r'(.+?)\s*-\s*(\d+)',
            # Anime Name 01
            r'(.+?)\s+(\d+)(?:\s|$)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, name, re.IGNORECASE)
            if match:
                anime_name = match.group(1).strip()
                episode = match.group(2) or match.group(3)
                
                # Clean up anime name
                anime_name = re.sub(r'[\.\-_]+', ' ', anime_name)
                anime_name = re.sub(r'\s+', ' ', anime_name).strip()
                
                # Remove common quality indicators
                anime_name = re.sub(r'\b(720p|1080p|480p|BD|BluRay|WEB|HDTV)\b', '', anime_name, flags=re.IGNORECASE)
                anime_name = anime_name.strip()
                
                return anime_name, episode
        
        # If no pattern matches, return original name
        return name, None
    
    def generate_new_filename(self, anime_name, episode, original_filename):
        """Generate a clean filename"""
        extension = os.path.splitext(original_filename)[1]
        
        if episode:
            # Pad episode number with zeros
            episode_num = str(episode).zfill(2)
            new_filename = f"{anime_name} - Episode {episode_num}{extension}"
        else:
            new_filename = f"{anime_name}{extension}"
        
        # Remove invalid characters for filename
        new_filename = re.sub(r'[<>:"/\\|?*]', '', new_filename)
        
        return new_filename
    
    async def handle_document(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle document/file uploads"""
        document = update.message.document
        
        # Check if it's a video file
        video_extensions = ['.mkv', '.mp4', '.avi', '.mov', '.wmv', '.flv', '.webm']
        if not any(document.file_name.lower().endswith(ext) for ext in video_extensions):
            await update.message.reply_text("Please send a video file (.mkv, .mp4, .avi, etc.)")
            return
        
        # Check file size (Telegram bot API has limits)
        if document.file_size > 1000 * 1024 * 1024:  # 50MB limit for demo
            await update.message.reply_text("File is too large. Please send files smaller than 50MB.")
            return
        
        await update.message.reply_chat_action(ChatAction.TYPING)
        
        try:
            # Extract anime info from filename
            anime_name, episode = self.extract_anime_info(document.file_name)
            new_filename = self.generate_new_filename(anime_name, episode, document.file_name)
            
            # Download the file
            await update.message.reply_text("📥 Downloading file...")
            file = await document.get_file()
            
            # Create temp directory if it doesn't exist
            os.makedirs("temp", exist_ok=True)
            
            # Download to temp location
            temp_path = f"temp/{document.file_name}"
            await file.download_to_drive(temp_path)
            
            # Rename file
            new_path = f"temp/{new_filename}"
            os.rename(temp_path, new_path)
            
            # Send renamed file back
            await update.message.reply_text(f"✅ Renamed to: `{new_filename}`", parse_mode='Markdown')
            
            with open(new_path, 'rb') as f:
                await update.message.reply_document(
                    document=f,
                    filename=new_filename,
                    caption=f"🎌 Renamed: {anime_name}" + (f" - Episode {episode}" if episode else "")
                )
            
            # Clean up temp files
            os.remove(new_path)
            
        except Exception as e:
            logger.error(f"Error processing file: {e}")
            await update.message.reply_text("❌ Sorry, there was an error processing your file.")
    
    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle text messages"""
        text = update.message.text
        
        # Test filename parsing
        if text.startswith("test:"):
            filename = text[5:].strip()
            anime_name, episode = self.extract_anime_info(filename)
            new_filename = self.generate_new_filename(anime_name, episode, filename)
            
            response = f"""
**Original:** `{filename}`
**Detected Anime:** {anime_name}
**Episode:** {episode if episode else 'Not detected'}
**New Filename:** `{new_filename}`
            """
            await update.message.reply_text(response, parse_mode='Markdown')
        else:
            await update.message.reply_text("Send me an anime file to rename, or use 'test: filename' to test parsing.")
    
    def run(self):
        """Start the bot"""
        print("🎌 Anime Auto Rename Bot starting...")
        
        # Start health check server in background if PORT is set (for web services)
        port = os.getenv('PORT')
        if port:
            def start_health_server():
                class HealthHandler(BaseHTTPRequestHandler):
                    def do_GET(self):
                        self.send_response(200)
                        self.send_header('Content-type', 'text/plain')
                        self.end_headers()
                        self.wfile.write(b'Bot is running!')
                    
                    def log_message(self, format, *args):
                        pass  # Suppress logs
                
                server = HTTPServer(('0.0.0.0', int(port)), HealthHandler)
                server.serve_forever()
            
            Thread(target=start_health_server, daemon=True).start()
            print(f"Health check server running on port {port}")
        
        self.app.run_polling(allowed_updates=Update.ALL_TYPES)

# Main execution
if __name__ == "__main__":
    # Get bot token from environment variable
    BOT_TOKEN = os.getenv('7921810145:AAGEm9Jq869GGKQXNK_FcRx1g6DrJZzjStY')
    
    if not BOT_TOKEN:
        print("❌ Please set BOT_TOKEN environment variable")
        print("Visit https://t.me/BotFather to create a new bot and get your token")
        exit(1)
    
    bot = AnimeRenameBot(BOT_TOKEN)
    bot.run()