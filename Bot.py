# -------------------------------
# bot.py - Invio report giornaliero su Telegram
# -------------------------------
import os
import requests
import yfinance as yf
import pandas as pd
import numpy as np
import feedparser
from datetime import datetime
from zoneinfo import ZoneInfo
from openai import OpenAI

# ============== CONFIGURAZIONE ==============
# LE CHIAVI ORA DEVONO ESSERE NELLE VARIABILI D'AMBIENTE
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

# Lista titoli da analizzare
STOCKS = ["SOUN", "RXRX", "PLTR", "AIQ"]

# Fuso orario
TZ = ZoneInfo("Europe/Rome")

# ============== OPENAI CLIENT ==============
client = OpenAI(api_key=OPENAI_API_KEY)

# ============== ANALISI TECNICA (RSI) ==============
def calculate_RSI(series, period=14):
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def get_stock_signal(ticker):
    try:
        data = yf.download(ticker, period="2mo", interval="1d", progress=False)
        if data.empty or len(data) < 20:
            return None, None, "⚠️ Dati insufficienti"

        data["RSI"] = calculate_RSI(data["Close"])
        last_rsi = float(data["RSI"].iloc[-1])
        last_close = float(data["Close"].iloc[-1])
        prev_close = float(data["Close"].iloc[-2])

        signal = "Aspetta"
        if last_rsi < 30 and last_close < prev_close:
            signal = "✅ Compra"
        elif last_rsi > 70 and last_close > prev_close:
            signal = "🚫 Vendi"

        return last_close, last_rsi, signal
    except Exception as e:
        return None, None, f"❌ Errore: {e}"

# ============== NEWS ==============
def get_news(max_items=5):
    try:
        feed = feedparser.parse("https://www.investing.com/rss/news_25.rss")
        headlines = []
        for entry in feed.entries[:max_items]:
            title = entry.title.replace("[", "(").replace("]", ")")
            headlines.append(f"📰 {title}")
        return headlines
    except Exception as e:
        return [f"❌ Errore lettura news: {e}"]

# ============== OPENAI CONSIGLIO ==============
def ask_gpt_for_advice(stock_data_rows):
    try:
        messages = [
            {"role": "system", "content": (
                "Sei un assistente finanziario professionale. "
                "Offri un breve riepilogo del sentiment e dei rischi in base a prezzo, RSI, e segnali 'Compra/Vendi/Aspetta'. "
                "Non dare garanzie; ricorda che non è consulenza finanziaria."
            )}
        ]
        for row in stock_data_rows:
            messages.append({"role": "user", "content": row})

        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.7,
            max_tokens=220,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        return f"Impossibile generare il consiglio IA ({e})."

# ============== TELEGRAM ==============
def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "Markdown"
    }
    r = requests.post(url, data=payload, timeout=30)
    r.raise_for_status()

# ============== COMPOSIZIONE MESSAGGIO ==============
def build_message():
    now = datetime.now(TZ)
    header = f"📊 *Report Mercato* – {now.strftime('%d %b %Y %H:%M %Z')}\n\n"

    lines = []
    gpt_rows = []
    for t in STOCKS:
        price, rsi, signal = get_stock_signal(t)
        if price is None or rsi is None:
            lines.append(f"{t}: {signal}")
        else:
            lines.append(f"{t}: ${price:.2f} | RSI: {rsi:.1f} → {signal}")
            gpt_rows.append(f"{t}: ${price:.2f}, RSI: {rsi:.1f}, Signal: {signal}")

    advice = ask_gpt_for_advice(gpt_rows)
    news = "\n".join(get_news())

    msg = (
        header +
        "\n".join(lines) +
        f"\n\n🔮 *Consiglio IA*: {advice}\n\n" +
        "📥 *Ultime Notizie:*\n" + news +
        "\n\n_(Questo non è un consiglio finanziario)_"
    )
    return msg[:4000]  # Telegram limite 4096 char

# ============== MAIN ==============
def main():
    if not TELEGRAM_TOKEN or not CHAT_ID or not OPENAI_API_KEY:
        raise RuntimeError(
            "Devi impostare TELEGRAM_TOKEN, CHAT_ID e OPENAI_API_KEY come variabili d'ambiente!"
        )

    message = build_message()
    send_telegram(message)
    print("✅ Report inviato.")

if __name__ == "__main__":
    main()
