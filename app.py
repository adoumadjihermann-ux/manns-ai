import os
import hmac
import requests
from flask import Flask, request, jsonify, render_template_string

app = Flask(__name__)
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

PAGE = r'''<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>MANN'S AI</title>
<style>
:root{color-scheme:dark}*{box-sizing:border-box}body{margin:0;background:#100d1c;color:#f8f6ff;font:16px system-ui,Arial;min-height:100vh;display:flex;justify-content:center;align-items:center;padding:14px}.app{width:100%;max-width:720px;height:min(850px,94vh);display:flex;flex-direction:column;background:#1a1530;border:1px solid #40335f;border-radius:22px;overflow:hidden;box-shadow:0 18px 55px #0006}.head{padding:18px;background:linear-gradient(120deg,#6d35c5,#34216d)}.head h1{margin:0;font-size:23px}.head p{margin:5px 0 0;color:#e5dafa;font-size:13px}.gate{padding:14px;display:flex;gap:8px;background:#211a39;border-bottom:1px solid #40335f}.gate input{flex:1;min-width:0}.messages{flex:1;overflow:auto;padding:16px;display:flex;flex-direction:column;gap:12px}.msg{padding:12px 14px;border-radius:15px;max-width:90%;white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.45}.user{align-self:flex-end;background:#6d35c5}.bot{align-self:flex-start;background:#2a2342;border:1px solid #40335f}.composer{display:flex;gap:8px;padding:12px;background:#211a39;border-top:1px solid #40335f}input,textarea,button{font:inherit;border-radius:12px;border:1px solid #59477d;padding:12px;background:#151126;color:#fff}button{background:#7b45d5;border:0;font-weight:700;cursor:pointer}button:disabled{opacity:.55}.composer input{flex:1;min-width:0}.hint{font-size:12px;color:#bdb1d7;padding:0 14px 12px}.error{color:#ffb8b8}
</style></head><body><main class="app"><header class="head"><h1>💜 MANN'S AI</h1><p>Ton assistant intelligent — version web</p></header>
<div class="gate"><input id="access" type="password" placeholder="Code d'accès fourni par le propriétaire" autocomplete="off"><button id="unlock">Accéder</button></div>
<div class="messages" id="messages"><div class="msg bot">Bonjour ! Je suis MANN'S AI. Entre le code d'accès que le propriétaire t'a communiqué, puis pose ta question. 🙂</div></div>
<form class="composer" id="form"><input id="question" placeholder="Écris ton message…" autocomplete="off" maxlength="3000"><button id="send" type="submit">Envoyer</button></form><div class="hint">Ne partage pas d'informations personnelles ou confidentielles.</div></main>
<script>
const $=id=>document.getElementById(id);let unlocked=false;let history=[];
$('unlock').onclick=()=>{if($('access').value.trim()){unlocked=true;$('access').disabled=true;$('unlock').textContent='Code saisi';$('messages').insertAdjacentHTML('beforeend','<div class="msg bot">Code saisi. Tu peux maintenant poser ta question.</div>')}else alert('Entre le code d’accès reçu.');};
function add(text,who){const d=document.createElement('div');d.className='msg '+who;d.textContent=text;$('messages').appendChild(d);$('messages').scrollTop=$('messages').scrollHeight;return d;}
$('form').addEventListener('submit',async e=>{e.preventDefault();const q=$('question').value.trim();if(!q)return;if(!unlocked){alert('Entre d’abord le code d’accès.');return;} $('question').value='';add(q,'user');history.push({role:'user',parts:[{text:q}]});const wait=add('MANN’S AI réfléchit…','bot');$('send').disabled=true;try{const r=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json','X-Access-Code':$('access').value},body:JSON.stringify({contents:history.slice(-12)})});const data=await r.json();wait.remove();if(!r.ok)throw new Error(data.error||'Erreur du serveur');const answer=data.answer||'Je n’ai pas de réponse pour le moment.';add(answer,'bot');history.push({role:'model',parts:[{text:answer}]});}catch(err){wait.remove();add('Erreur : '+err.message,'bot');}finally{$('send').disabled=false;$('question').focus();}});
</script></body></html>'''

@app.get("/")
def home():
    return render_template_string(PAGE)

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/api/chat")
def chat():
    expected = os.getenv("ACCESS_CODE", "")
    supplied = request.headers.get("X-Access-Code", "")
    if not expected:
        return jsonify(error="Le propriétaire doit configurer ACCESS_CODE sur le serveur."), 503
    if not hmac.compare_digest(supplied, expected):
        return jsonify(error="Code d'accès incorrect."), 401

    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        return jsonify(error="La clé Gemini n'est pas configurée sur le serveur."), 503

    payload = request.get_json(silent=True) or {}
    contents = payload.get("contents", [])
    if not isinstance(contents, list) or not contents:
        return jsonify(error="Écris d'abord une question."), 400
    safe_contents = []
    for item in contents[-12:]:
        if not isinstance(item, dict) or item.get("role") not in ("user", "model"):
            continue
        parts = item.get("parts", [])
        if not isinstance(parts, list):
            continue
        text_parts = [p.get("text", "")[:3000] for p in parts if isinstance(p, dict) and isinstance(p.get("text"), str)]
        if text_parts:
            safe_contents.append({"role": item["role"], "parts": [{"text": "\n".join(text_parts)}]})
    if not safe_contents or safe_contents[-1]["role"] != "user":
        return jsonify(error="Question invalide."), 400

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
    try:
        response = requests.post(url, params={"key": api_key}, json={"contents": safe_contents, "generationConfig": {"maxOutputTokens": 700}}, timeout=60)
        if response.status_code >= 400:
            return jsonify(error="Le service IA a refusé la demande. Vérifie les quotas, le modèle et la clé API dans les paramètres du propriétaire."), 502
        data = response.json()
        answer = "".join(part.get("text", "") for part in data.get("candidates", [{}])[0].get("content", {}).get("parts", []) if isinstance(part, dict))
        if not answer:
            return jsonify(error="Le service IA n'a pas renvoyé de texte. Réessaie."), 502
        return jsonify(answer=answer)
    except requests.Timeout:
        return jsonify(error="Le service IA met trop de temps à répondre. Réessaie."), 504
    except requests.RequestException:
        return jsonify(error="Impossible de joindre le service IA. Vérifie la connexion du serveur."), 502

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "10000")))
