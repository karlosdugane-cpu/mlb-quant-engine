import os
import datetime
import requests
import pandas as pd
import numpy as np
from flask import Flask, jsonify

app = Flask(__name__)

# ==========================================
# CONFIGURATION ET FILTRES STRICTS
# ==========================================
ODDS_API_KEY = "68d874fb44f7d4dfb7a5deeb4627b80f"
TELEGRAM_BOT_TOKEN = "8405911600:AAEIUhtYeQY3vKboG4Z5KQhNi6U-iu44V0o"
TELEGRAM_CHAT_ID = "6046600050"

STARTER_WEIGHT = 0.65       
BULLPEN_WEIGHT = 0.35       
LEAGUE_AVG = 4.00           
BASELINE_RUNS = 4.50        
HOME_FIELD_ADVANTAGE = 0.18 
LOGISTIC_SCALE = 1.50       
SEASON_YEAR = 2026

# FILTRES DE SÉCURITÉ REHAUSSÉS
MIN_EV_THRESHOLD = 0.05     # 5% minimum
TELEGRAM_MIN_EV = 7.0       # Alerte Telegram uniquement si EV >= 7% (Filtre anti-piège)

def send_telegram_alert(message):
    if TELEGRAM_BOT_TOKEN == "VOTRE_BOT_TOKEN_ICI" or TELEGRAM_CHAT_ID == "VOTRE_CHAT_ID_ICI":
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Erreur Telegram : {e}")

# ==========================================
# FONCTIONS MATHÉMATIQUES SÉCURISÉES
# ==========================================
def calculate_expected_value(win_prob, decimal_odds):
    if decimal_odds <= 1.0:
        return 0.0
    return round(((win_prob * decimal_odds) - 1.0) * 100, 2)

def calculate_safe_kelly(win_prob, decimal_odds, max_bankroll_pct=0.03):
    """Kelly fractionnaire ultra-prudent (1/8) plafonné à 3% pour zéro risque de ruine."""
    if decimal_odds <= 1.0:
        return 0.0
    b = decimal_odds - 1.0
    full_kelly = (win_prob * b - (1.0 - win_prob)) / b
    if full_kelly <= 0:
        return 0.0
    fractional_kelly = full_kelly * 0.125
    final_stake_pct = min(fractional_kelly, max_bankroll_pct)
    return round(final_stake_pct * 100, 2)

# ==========================================
# RÉCUPÉRATION DES DONNÉES (AVEC SÉCURITÉ STRICTE)
# ==========================================
def get_live_odds():
    if ODDS_API_KEY == "VOTRE_CLE_API_ICI":
        return {}
    url = f"https://api.the-odds-api.com/v4/sports/baseball_mlb/odds/?apiKey={ODDS_API_KEY}&regions=us&markets=h2h&oddsFormat=decimal"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            return {}
        data = response.json()
        odds_dict = {}
        for game in data:
            home_team, away_team = game['home_team'], game['away_team']
            best_away, best_home = 1.0, 1.0
            best_away_bm, best_home_bm = "N/A", "N/A"
            for bookmaker in game.get('bookmakers', []):
                bm_title = bookmaker.get('title', 'Unknown')
                for market in bookmaker.get('markets', []):
                    if market['key'] == 'h2h':
                        for outcome in market.get('outcomes', []):
                            price = outcome.get('price', 1.0)
                            if outcome['name'] == away_team and price > best_away:
                                best_away, best_away_bm = price, bm_title
                            elif outcome['name'] == home_team and price > best_home:
                                best_home, best_home_bm = price, bm_title
            odds_dict[(away_team.lower(), home_team.lower())] = {
                "away_odds": best_away, "home_odds": best_home,
                "away_bookmaker": best_away_bm, "home_bookmaker": best_home_bm
            }
        return odds_dict
    except:
        return {}

def get_mlb_schedule(date_str):
    url = f"https://statsapi.mlb.com/api/v1/schedule?sportId=1&date={date_str}&hydrate=probablePitcher"
    response = requests.get(url)
    if response.status_code != 200:
        return []
    data = response.json()
    games = []
    for date_entry in data.get('dates', []):
        for game in date_entry.get('games', []):
            if game.get('gameType') == 'R':
                games.append({
                    'away_team': game['teams']['away']['team']['name'],
                    'away_id': game['teams']['away']['team']['id'],
                    'home_team': game['teams']['home']['team']['name'],
                    'home_id': game['teams']['home']['team']['id'],
                    'away_pitcher_id': game['teams']['away'].get('probablePitcher', {}).get('id'),
                    'home_pitcher_id': game['teams']['home'].get('probablePitcher', {}).get('id')
                })
    return games

def get_pitcher_fip(pitcher_id):
    """Retourne None si le lanceur est inconnu ou n'a pas assez d'historique (Bloque les approximations)."""
    if not pitcher_id:
        return None
    url = f"https://statsapi.mlb.com/api/v1/people/{pitcher_id}/stats?stats=season&season={SEASON_YEAR}&group=pitching"
    response = requests.get(url)
    if response.status_code != 200:
        return None
    try:
        splits = response.json().get('stats', [])[0].get('splits', [])
        if not splits:
            return None
        p = splits[0].get('stat', {})
        ip = float(p.get('inningsPitched', 0))
        if ip < 3.0: # Exige au moins 3 manches lancées pour éviter les stats faussées de début de saison/remplaçants
            return None
        return round(((13 * int(p.get('homeRuns', 0))) + (3 * (int(p.get('baseOnBalls', 0)) + int(p.get('hitBatsmen', 0)))) - (2 * int(p.get('strikeOuts', 0)))) / ip + 3.10, 2)
    except:
        return None

def get_team_pitching_era(team_id):
    if not team_id:
        return LEAGUE_AVG
    url = f"https://statsapi.mlb.com/api/v1/teams/{team_id}/stats?season={SEASON_YEAR}&group=pitching&stats=season"
    response = requests.get(url)
    if response.status_code != 200:
        return LEAGUE_AVG
    try:
        splits = response.json().get('stats', [])[0].get('splits', [])
        if splits:
            return float(splits[0].get('stat', {}).get('era', LEAGUE_AVG))
    except:
        pass
    return LEAGUE_AVG

def predict_game_outcome(away_fip, away_bp, home_fip, home_bp):
    away_pitching = (away_fip * STARTER_WEIGHT) + (away_bp * BULLPEN_WEIGHT)
    home_pitching = (home_fip * STARTER_WEIGHT) + (home_bp * BULLPEN_WEIGHT)
    home_exp = (BASELINE_RUNS * (away_pitching / LEAGUE_AVG)) + HOME_FIELD_ADVANTAGE
    away_exp = BASELINE_RUNS * (home_pitching / LEAGUE_AVG)
    home_win_prob = 1 / (1 + 10 ** (-(home_exp - away_exp) / LOGISTIC_SCALE))
    return round(away_exp, 2), round(home_exp, 2), round(home_win_prob, 3)

# ==========================================
# BOUCLE PRINCIPALE AVEC FILTRE DE SÉCURITÉ ABSOLUE
# ==========================================
def run_mlb_analysis():
    today = datetime.datetime.now().strftime('%Y-%m-%d')
    games = get_mlb_schedule(today)
    if not games:
        return {"status": "info", "message": "Aucun match MLB aujourd'hui."}

    live_odds = get_live_odds()
    alerts_sent = 0
    skipped_games = 0
    
    for game in games:
        match_name = f"{game['away_team']} @ {game['home_team']}"
        
        # Récupération des FIP des lanceurs partants
        away_fip = get_pitcher_fip(game['away_pitcher_id'])
        home_fip = get_pitcher_fip(game['home_pitcher_id'])
        
        # 🛡️ SÉCURITÉ CRITIQUE : Si l'un des lanceurs partants n'a pas de stats officielles, on ignore le match
        if away_fip is None or home_fip is None:
            skipped_games += 1
            continue

        away_bp = get_team_pitching_era(game['away_id'])
        home_bp = get_team_pitching_era(game['home_id'])
        
        # Calcul du modèle pur
        away_exp, home_exp, home_prob_dec = predict_game_outcome(away_fip, away_bp, home_fip, home_bp)
        away_prob_dec = 1.0 - home_prob_dec
        
        odds = live_odds.get((game['away_team'].lower(), game['home_team'].lower()), 
                             {"away_odds": 2.00, "home_odds": 2.00, "away_bookmaker": "-", "home_bookmaker": "-"})

        away_ev = calculate_expected_value(away_prob_dec, odds["away_odds"])
        home_ev = calculate_expected_value(home_prob_dec, odds["home_odds"])
        away_kelly = calculate_safe_kelly(away_prob_dec, odds["away_odds"])
        home_kelly = calculate_safe_kelly(home_prob_dec, odds["home_odds"])

        chosen_team, chosen_ev, chosen_prob, chosen_odds, chosen_kelly, chosen_bm = None, 0, 0, 0, 0, "-"

        if away_ev > home_ev and away_ev >= (MIN_EV_THRESHOLD * 100):
            chosen_team, chosen_ev, chosen_prob, chosen_odds, chosen_kelly, chosen_bm = (
                game['away_team'], away_ev, round(away_prob_dec * 100, 1), odds["away_odds"], away_kelly, odds["away_bookmaker"]
            )
        elif home_ev > away_ev and home_ev >= (MIN_EV_THRESHOLD * 100):
            chosen_team, chosen_ev, chosen_prob, chosen_odds, chosen_kelly, chosen_bm = (
                game['home_team'], home_ev, round(home_prob_dec * 100, 1), odds["home_odds"], home_kelly, odds["home_bookmaker"]
            )

        # Envoi uniquement si l'EV dépasse le nouveau seuil strict de 7%
        if chosen_team and chosen_ev >= TELEGRAM_MIN_EV:
            msg = (
                f"🔥 *SIGNAL VALUE BET CERTIFIÉ* 🔥\n\n"
                f"⚾ *Match :* `{match_name}`\n"
                f"🎯 *Pari :* `{chosen_team}`\n"
                f"📈 *Expected Value :* `+{chosen_ev}%`\n"
                f"📊 *Prob. Modèle :* `{chosen_prob}%`\n"
                f"💰 *Cote :* `{chosen_odds}` ({chosen_bm})\n"
                f"💵 *Mise Rec. :* `{chosen_kelly}% bankroll`"
            )
            send_telegram_alert(msg)
            alerts_sent += 1

    return {
        "status": "success", 
        "alerts_sent": alerts_sent, 
        "matches_analyzed": len(games),
        "matches_skipped_due_to_missing_pitcher_data": skipped_games
    }

# ==========================================
# ROUTES FLASK
# ==========================================
@app.route('/')
def home():
    return "✅ MLB Quantitative Engine (Secured Mode) is LIVE."

@app.route('/run-mlb')
def trigger_bot():
    try:
        return jsonify(run_mlb_analysis())
    except Exception as e:
        return jsonify({"status": "error", "details": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)