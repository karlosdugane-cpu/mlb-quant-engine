import os
import requests
import numpy as np
from flask import Flask, jsonify

app = Flask(__name__)

# ==========================================
# 1. PARAMÈTRES ET CONFIGURATION TELEGRAM
# ==========================================
TELEGRAM_BOT_TOKEN = os.getenv("8405911600:AAEIUhtYeQY3vKboG4Z5KQhNi6U-iu44V0o", "8405911600:AAEIUhtYeQY3vKboG4Z5KQhNi6U-iu44V0o")
TELEGRAM_CHAT_ID = os.getenv("6046600050", "6046600050")

def send_telegram_alert(message):
    """Envoie le rapport généré sur ton canal Telegram."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
    except Exception as e:
        print(f"Erreur d'envoi Telegram : {e}")

# ==========================================
# 2. MOTEUR MATHÉMATIQUE (CORRECTIONS)
# ==========================================
def cap_and_smooth_probability(raw_prob, max_cap=0.68, min_cap=0.32):
    """Lisse les probabilités pour refléter la réalité de la MLB."""
    smoothed_prob = (raw_prob * 0.7) + (0.50 * 0.3)
    return float(np.clip(smoothed_prob, min_cap, max_cap))

def calculate_safe_kelly(prob, odds, max_bankroll_pct=0.03):
    """Fractional Kelly (1/8) plafonné à 3% de la bankroll."""
    b = odds - 1
    full_kelly = (b * prob - (1 - prob)) / b
    
    if full_kelly <= 0:
        return 0.0
    
    fractional_kelly = full_kelly * 0.125
    final_stake_pct = min(fractional_kelly, max_bankroll_pct)
    return round(final_stake_pct * 100, 2)

def calculate_ev(prob, odds):
    """Calcule l'Expected Value réel."""
    ev = (prob * odds) - 1
    return round(ev * 100, 2)

# ==========================================
# 3. ROUTES DU SERVEUR WEB (POUR RENDER)
# ==========================================
@app.route('/')
def home():
    """Endpoint de santé pour UptimeRobot (Méthode GET)."""
    return "✅ MLB Quantitative Engine is LIVE.", 200

@app.route('/run-mlb')
def run_mlb_analysis():
    """Déclencheur quotidien pour Cron-job.org."""
    
    # ---------------------------------------------------------
    # ⚠️ ZONE À COMPLÉTER AVEC TON CODE ACTUEL ⚠️
    # C'est ici que tu dois insérer ton code qui télécharge 
    # les matchs du jour et fait tourner ton modèle (ex: XGBoost/RandomForest).
    # ---------------------------------------------------------
    
    # EXEMPLE FICTIF DE CE QUE TON MODÈLE DOIT RENVOYER :
    match_name = "San Diego Padres @ Cincinnati Reds"
    bet_pick = "San Diego Padres"
    raw_model_prob = 0.957 # L'ancienne probabilité brute délirante
    best_odds = 1.69
    bookmaker = "BetOnline.ag"
    
    # --- APPLICATION DES CORRECTIONS MATHÉMATIQUES ---
    safe_prob = cap_and_smooth_probability(raw_model_prob) # Va passer de 95.7% à environ ~68%
    real_ev = calculate_ev(safe_prob, best_odds)
    safe_kelly_stake = calculate_safe_kelly(safe_prob, best_odds)
    
    # --- CONSTRUCTION DU MESSAGE TELEGRAM ---
    if safe_kelly_stake > 0:
        message = (
            f"⚾️ <b>Match :</b> {match_name}\n"
            f"🎯 <b>Pari :</b> {bet_pick}\n"
            f"📈 <b>Expected Value :</b> +{real_ev}%\n"
            f"📊 <b>Prob. Modèle (Calibrée) :</b> {round(safe_prob * 100, 1)}%\n"
            f"💰 <b>Cote :</b> {best_odds} ({bookmaker})\n"
            f"💵 <b>Mise Rec. :</b> {safe_kelly_stake}% bankroll"
        )
        send_telegram_alert(message)
        return jsonify({"status": "success", "message": "Analyse terminée, alerte envoyée."}), 200
    else:
        return jsonify({"status": "success", "message": "Aucun pari EV+ trouvé aujourd'hui."}), 200

# ==========================================
# LANCEMENT LOCAL
# ==========================================
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)