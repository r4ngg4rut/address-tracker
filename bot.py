import os
import json
import requests
from web3 import Web3
from telegram import Update
from telegram.ext import Updater, CommandHandler, CallbackContext
from solana.rpc.api import Client as SolanaClient
from solana.publickey import PublicKey

# Load Environment Variables
HEROKU_APP_NAME = os.getenv("HEROKU_APP_NAME")  # Nama Aplikasi Heroku
HEROKU_API_KEY = os.getenv("HEROKU_API_KEY")  # API Key Heroku
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

# Load RPC URLs dari File JSON
with open("rpc_config.json", "r") as f:
    RPC_URLS = json.load(f)

# Initialize Web3 clients untuk jaringan EVM
web3_clients = {chain: Web3(Web3.HTTPProvider(url)) for chain, url in RPC_URLS.items() if chain != "solana"}

# Initialize Solana client
solana_client = SolanaClient(RPC_URLS.get("solana"))

# Initialize Telegram Bot
updater = Updater(token=TELEGRAM_TOKEN, use_context=True)
dispatcher = updater.dispatcher

def update_heroku_config(key, value):
    """Update Config Vars di Heroku menggunakan API"""
    url = f"https://api.heroku.com/apps/{HEROKU_APP_NAME}/config-vars"
    headers = {
        "Accept": "application/vnd.heroku+json; version=3",
        "Authorization": f"Bearer {HEROKU_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {key: value}
    response = requests.patch(url, headers=headers, json=data)
    
    return response.status_code == 200

def add_address(update: Update, context: CallbackContext):
    """Handle /addaddress command"""
    if len(context.args) != 2:
        update.message.reply_text("Usage: /addaddress <network> <wallet_address>")
        return

    network, address = context.args
    network = network.lower()

    if network in RPC_URLS:
        key = f"TRACKED_{network.upper()}_ADDRESS"
        network_name = network.upper()
    elif network == "solana":
        key = "TRACKED_SOLANA_ADDRESS"
        network_name = "Solana"
    elif network == "ton":
        key = "TRACKED_TON_ADDRESS"
        network_name = "TON"
    else:
        update.message.reply_text("Invalid network! Use: eth/bsc/polygon/base/op/morph/solana/ton")
        return

    # Ambil address lama, tambahkan address baru, lalu update ke Heroku
    old_addresses = os.getenv(key, "").split(",")
    if address in old_addresses:
        update.message.reply_text(f"⚠️ Address {address} sudah ditambahkan sebelumnya!")
        return

    new_addresses = ",".join(filter(None, old_addresses + [address]))

    if update_heroku_config(key, new_addresses):
        update.message.reply_text(f"✅ Address {address} berhasil ditambahkan ke {network_name}")
    else:
        update.message.reply_text("❌ Gagal menyimpan address ke Heroku!")

def check_balance(update: Update, context: CallbackContext):
    """Handle /balance command"""
    if len(context.args) != 2:
        update.message.reply_text("Usage: /balance <network> <wallet_address>")
        return

    network, address = context.args
    network = network.lower()

    if network in web3_clients:
        web3 = web3_clients.get(network)
        try:
            balance_wei = web3.eth.get_balance(address)
            balance_eth = web3.from_wei(balance_wei, 'ether')
            message = f"💰 Saldo {network.upper()}: {balance_eth:.4f} {network.upper()}"
        except Exception as e:
            message = f"⚠️ Gagal mengambil saldo {network.upper()}: {str(e)}"
    elif network == "solana":
        try:
            pubkey = PublicKey(address)
            balance = solana_client.get_balance(pubkey)['result']['value'] / 1e9
            message = f"💰 Saldo SOLANA: {balance:.4f} SOL"
        except Exception as e:
            message = f"⚠️ Gagal mengambil saldo SOLANA: {str(e)}"
    elif network == "ton":
        try:
            response = requests.get(f"https://tonapi.io/v1/account/getInfo?account={address}")
            data = response.json()
            balance = data['balance'] / 1e9
            message = f"💰 Saldo TON: {balance:.4f} TON"
        except Exception as e:
            message = f"⚠️ Gagal mengambil saldo TON: {str(e)}"
    else:
        message = "❌ Jaringan tidak dikenali! Gunakan: eth/bsc/polygon/base/op/morph/solana/ton"

    update.message.reply_text(message)

# Register Telegram Commands
dispatcher.add_handler(CommandHandler("addaddress", add_address))
dispatcher.add_handler(CommandHandler("balance", check_balance))

# Start the bot
if __name__ == "__main__":
    print("🚀 Bot is running...")
    updater.start_polling()
