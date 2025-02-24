import os
import json
import time
import requests
from web3 import Web3
from telegram import Update
from telegram.ext import Updater, CommandHandler, CallbackContext
from solana.rpc.api import Client as SolanaClient
from solana.publickey import PublicKey

# Load Environment Variables
HEROKU_APP_NAME = os.getenv("HEROKU_APP_NAME")
HEROKU_API_KEY = os.getenv("HEROKU_API_KEY")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

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

def send_telegram_message(message):
    """Kirim notifikasi ke Telegram"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": CHAT_ID, "text": message}
    requests.post(url, data=data)

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
    
    if network == "evm":
        key = "TRACKED_EVM_ADDRESS"
        network_name = "EVM (ETH, BSC, Polygon, dll.)"
    elif network == "solana":
        key = "TRACKED_SOLANA_ADDRESS"
        network_name = "Solana"
    elif network == "ton":
        key = "TRACKED_TON_ADDRESS"
        network_name = "TON"
    else:
        update.message.reply_text("Invalid network! Use: evm/solana/ton")
        return

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
    
    if network == "evm":
        messages = []
        for chain, web3 in web3_clients.items():
            try:
                balance_wei = web3.eth.get_balance(address)
                balance_eth = web3.from_wei(balance_wei, 'ether')
                messages.append(f"💰 {chain.upper()}: {balance_eth:.4f}")
            except Exception as e:
                messages.append(f"⚠️ {chain.upper()} error: {str(e)}")
        message = "\n".join(messages)
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
            balance = data.get('balance', 0) / 1e9
            message = f"💰 Saldo TON: {balance:.4f} TON"
        except Exception as e:
            message = f"⚠️ Gagal mengambil saldo TON: {str(e)}"
    else:
        message = "❌ Jaringan tidak dikenali! Gunakan: evm/solana/ton"

    update.message.reply_text(message)

def monitor_transactions():
    """Pantau transaksi masuk dan keluar"""
    tracked_addresses = os.getenv("TRACKED_EVM_ADDRESS", "").split(",")

    while True:
        for chain, web3 in web3_clients.items():
            try:
                latest_block = web3.eth.block_number
                block = web3.eth.get_block(latest_block, full_transactions=True)

                for tx in block.transactions:
                    if tx.to and tx.to.lower() in tracked_addresses:
                        send_telegram_message(f"📥 Incoming Transaction\n🔹 Network: {chain.upper()}\n🔹 To: {tx.to}\n🔹 Amount: {web3.from_wei(tx.value, 'ether')} ETH")
                    elif tx["from"].lower() in tracked_addresses:
                        send_telegram_message(f"📤 Outgoing Transaction\n🔹 Network: {chain.upper()}\n🔹 From: {tx['from']}\n🔹 Amount: {web3.from_wei(tx.value, 'ether')} ETH")
            except Exception as e:
                print(f"⚠️ Error monitoring {chain}: {str(e)}")

        time.sleep(1)

# Register Telegram Commands
dispatcher.add_handler(CommandHandler("addaddress", add_address))
dispatcher.add_handler(CommandHandler("balance", check_balance))

if __name__ == "__main__":
    print("�� Bot is running...")
    
    # Jalankan pemantauan transaksi dalam thread terpisah
    import threading
    t = threading.Thread(target=monitor_transactions)
    t.daemon = True
    t.start()
    
    updater.start_polling()
