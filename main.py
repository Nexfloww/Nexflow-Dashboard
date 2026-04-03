import os, json, time, base64, random
from datetime import datetime
from email.mime.text import MIMEText
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from groq import Groq

# CONFIG
GMAIL_SENDER = "nexflow.ia@gmail.com"
GOOGLE_PLACES_API_KEY = os.environ.get("GOOGLE_PLACES_API_KEY", "")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
HISTORIQUE_PATH = os.path.expanduser("~/prospection-restos/historique.json")
LIMIT_MOIS = 75  # emails max par mois

# Zones autour de Conflans - organisées par vagues mensuelles
ZONES = [
    # Vague 1 - Proches
    ["Conflans-Sainte-Honorine", "Cergy", "Pontoise", "Poissy", "Sartrouville"],
    # Vague 2 - Moyens
    ["Saint-Germain-en-Laye", "Argenteuil", "Acheres", "Mantes-la-Jolie", "Versailles"],
    # Vague 3 - Plus loin
    ["Rambouillet", "Meulan", "Les Mureaux", "Nanterre", "Colombes"],
    # Vague 4
    ["Chatou", "Le Pecq", "Maisons-Laffitte", "Houilles", "Franconville"],
    # Vague 5
    ["Ermont", "Eaubonne", "Saint-Leu-la-Foret", "Taverny", "Herblay"],
]

def get_villes_du_mois():
    mois_index = datetime.now().month - 1  # 0 à 11
    zone_index = mois_index % len(ZONES)
    return ZONES[zone_index]

def charger_historique():
    try:
        with open(HISTORIQUE_PATH, "r") as f:
            return json.load(f)
    except:
        return []

def sauvegarder_historique(historique):
    with open(HISTORIQUE_PATH, "w") as f:
        json.dump(historique, f, ensure_ascii=False, indent=2)

def deja_contacte(historique, nom, ville):
    for h in historique:
        if h["nom"].lower() == nom.lower() and h["ville"].lower() == ville.lower():
            return True
    return False

def get_gmail_service():
    creds = Credentials.from_authorized_user_file(
        os.path.expanduser("~/prospection-restos/token.json")
    )
    return build("gmail", "v1", credentials=creds)

def find_restaurants_google(ville):
    import urllib.request
    url = (
        f"https://maps.googleapis.com/maps/api/place/textsearch/json"
        f"?query=restaurant+independant+{ville.replace(' ', '+')}"
        f"&key={GOOGLE_PLACES_API_KEY}&language=fr"
    )
    with urllib.request.urlopen(url) as r:
        data = json.loads(r.read())
    restos = []
    for place in data.get("results", []):
        types = place.get("types", [])
        if any(t in types for t in ["restaurant", "food", "meal_takeaway"]):
            place_id = place["place_id"]
            detail_url = (
                f"https://maps.googleapis.com/maps/api/place/details/json"
                f"?place_id={place_id}&fields=name,website,formatted_phone_number"
                f"&key={GOOGLE_PLACES_API_KEY}&language=fr"
            )
            with urllib.request.urlopen(detail_url) as r2:
                detail = json.loads(r2.read()).get("result", {})
            restos.append({
                "name": place["name"],
                "ville": ville,
                "website": detail.get("website", ""),
                "phone": detail.get("formatted_phone_number", ""),
            })
            time.sleep(0.2)
    return restos

def generate_email(resto):
    client = Groq(api_key=GROQ_API_KEY)
    prompt = f"""Tu es Soraya, fondatrice de Nexflow. Écris un email de prospection court et percutant pour {resto['name']} à {resto['ville']}.
Nexflow = IA qui répond aux appels 24h/24, prend les commandes, dashboard simple.
Propose une démo gratuite 15 min. Site: https://nexfloww.github.io/Nexflow
Email: nexflow.ia@gmail.com
Signe: Soraya, Nexflow
3 paragraphes max, pas de formule générique."""
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=400
    )
    return response.choices[0].message.content

def send_email(service, to, subject, body):
    message = MIMEText(body)
    message["to"] = to
    message["from"] = GMAIL_SENDER
    message["subject"] = subject
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    service.users().messages().send(userId="me", body={"raw": raw}).execute()
    print(f"✅ Email envoye a {to}")

def main():
    historique = charger_historique()
    villes = get_villes_du_mois()
    
    # Compter emails du mois en cours
    mois_actuel = datetime.now().strftime("%m/%Y")
    emails_ce_mois = sum(1 for h in historique if h.get("date", "").endswith(mois_actuel[3:]) and h.get("date", "")[3:5] == mois_actuel[:2])
    
    print(f"🚀 Nexflow Prospection - {datetime.now().strftime('%B %Y')}")
    print(f"📍 Villes ce mois: {', '.join(villes)}")
    print(f"📊 Emails envoyés ce mois: {emails_ce_mois}/{LIMIT_MOIS}")
    
    if emails_ce_mois >= LIMIT_MOIS:
        print("⛔ Limite mensuelle atteinte. Relance le mois prochain !")
        return

    service = get_gmail_service()
    tous_restos = []
    for ville in villes:
        print(f"🔍 Recherche à {ville}...")
        restos = find_restaurants_google(ville)
        tous_restos.extend(restos)
        time.sleep(1)

    # Dédoublonner et filtrer déjà contactés
    vus = set()
    restos_filtres = []
    for r in tous_restos:
        key = f"{r['name'].lower()}_{r['ville'].lower()}"
        if key not in vus and r.get("website") and not deja_contacte(historique, r["name"], r["ville"]):
            vus.add(key)
            restos_filtres.append(r)

    random.shuffle(restos_filtres)
    print(f"✅ {len(restos_filtres)} nouveaux restos avec site trouvés")

    envoyes = 0
    for resto in restos_filtres:
        if emails_ce_mois + envoyes >= LIMIT_MOIS:
            print(f"⛔ Limite de {LIMIT_MOIS} emails atteinte pour ce mois !")
            break
        
        print(f"\n✍️  Rédaction pour {resto['name']} ({resto['ville']})...")
        try:
            body = generate_email(resto)
            subject = f"Vous perdez des commandes chaque jour - {resto['name']}"
            send_email(service, "nexflow.ia@gmail.com", subject, body)  # TEST - remplacer par vraie adresse
            
            historique.append({
                "nom": resto["name"],
                "ville": resto["ville"],
                "site": resto.get("website", ""),
                "telephone": resto.get("phone", ""),
                "sujet": subject,
                "statut": "envoyé",
                "date": datetime.now().strftime("%d/%m/%Y"),
                "timestamp": datetime.now().isoformat()
            })
            sauvegarder_historique(historique)
            envoyes += 1
            time.sleep(2)
        except Exception as e:
            print(f"❌ Erreur: {e}")
            time.sleep(10)

    print(f"\n🎉 Terminé ! {envoyes} emails envoyés ce mois.")

if __name__ == "__main__":
    main()
