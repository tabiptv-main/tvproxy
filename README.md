# 📺 tvproxy

## 🚀 M3U8 Proxy Dockerizzato

Un server proxy leggero basato su **Flask** e **Requests**, progettato per:

- 📥 Scaricare e modificare flussi **.m3u / .m3u8**
- 🔁 Proxare i segmenti `.ts`, mantenendo header personalizzati
- 🚫 Superare restrizioni come **Referer**, **User-Agent**, ecc.
- 🐳 Essere facilmente **dockerizzabile** su qualsiasi macchina o server

---

## ☁️ Deploy su Render (I canali DLHD funzionano solo con Proxy SOCKS5)

1.  Vai su **Projects → Deploy a Web Service → Public Git Repo**
2.  Inserisci il repo: `https://github.com/nzo66/tvproxy` → **Connect**
3.  Dai un nome a piacere
4.  Imposta **Instance Type** su `Free`
5.  **Configura le variabili d'ambiente per il proxy:**
    *   Nella sezione **Environment**, aggiungi una nuova variabile.
    *   **Key:** `NEWKSO_PROXY_SOCKS5`
    *   **Value:** `socks5h://user:pass@host:port` (sostituisci con i tuoi dati del proxy)
    > ℹ️ Per maggiori dettagli sul formato del proxy, consulta la sezione Configurazione Proxy.
6.  Clicca su **Deploy Web Service**

---

## 🤗 Deploy su HuggingFace (I canali DLHD funzionano solo con Proxy SOCKS5)

`ricora di fare factory rebuild per aggiornare il proxy se ci sono aggiornamenti!`

1. Crea un nuovo **Space**
2. Scegli un nome qualsiasi e imposta **Docker** come tipo
3. Lascia **Public** e crea lo Space
4. Vai in alto a destra → `⋮` → **Files** → carica **DockerfileHF** rinominandolo **Dockerfile**
5. **Configura le variabili d'ambiente per il proxy:**
    *   Vai su **Settings** (Impostazioni) del tuo Space.
    *   Nella sezione **Environment Secret**, aggiungi una nuova variabile secret.
    *   **Name:** `NEWKSO_PROXY_SOCKS5`
    *   **Value:** `socks5h://user:pass@host:port` (sostituisci con i tuoi dati del proxy)
    > ℹ️ Per maggiori dettagli sul formato del proxy, consulta la sezione Configurazione Proxy.
6.  Infine vai su `⋮` → **Embed this Space** per ottenere il **Direct URL**

---

## 🐳 Docker (Locale o Server)

### ✅ Costruzione e Avvio

1.  **Clona e costruisci l'immagine:**
    ```bash
    git clone https://github.com/nzo66/tvproxy.git
    cd tvproxy
    docker build -t tvproxy .
    ```

2.  **Avvia il container:**

    *   **Senza proxy:**
        ```bash
        docker run -d -p 7860:7860 --name tvproxy tvproxy
        ```

    *   **Con un proxy (esempio):**
        Per usare un proxy, passa le variabili d'ambiente con l'opzione `-e`.
        ```bash
        docker run -d -p 7860:7860 -e NEWKSO_PROXY_SOCKS5="socks5h://user:pass@host:port" --name tvproxy tvproxy
        ```
        > ℹ️ Per maggiori dettagli sulla configurazione dei proxy, consulta la sezione Configurazione Proxy.

---

## 🐧 Termux (Dispositivi Android)

### ✅ Costruzione e Avvio

# 1. Installa i pacchetti necessari (incluso l'editor nano)
pkg install git python nano -y

# 2. Clona il repository e accedi alla cartella
git clone https://github.com/nzo66/tvproxy.git
cd tvproxy

# 3. Installa le dipendenze Python
pip install -r requirements.txt

# 4. (Opzionale) Crea il file .env per il proxy
nano .env
```
Dopo aver eseguito `nano .env`, incolla la configurazione del tuo proxy (esempio sotto), poi salva il file premendo `Ctrl+X`, poi `Y`, e infine `Invio`.
```
# Esempio di contenuto per il file .env
NEWKSO_PROXY_SOCKS5="socks5h://user:pass@host:port"
```
```bash
# 5. Avvia il server con Gunicorn
gunicorn app:app -w 4 --worker-class gevent --worker-connections 100 -b 0.0.0.0:7860 --timeout 120 --keep-alive 5 --max-requests 1000 --max-requests-jitter 100

---

## 🐍 Avvio con Python (Locale)

### ✅ Setup e Avvio

# 1. Clona il repository
git clone https://github.com/nzo66/tvproxy.git
cd tvproxy

# 2. Installa le dipendenze
pip install -r requirements.txt

```
Per configurare un proxy senza dover usare il comando `export`, puoi creare un file `.env`.
```bash
# 3. (Opzionale) Crea e modifica il file .env con nano (o il tuo editor preferito)
nano .env
```
Aggiungi la variabile del proxy al file (lo script la caricherà automaticamente):
```
NEWKSO_PROXY_SOCKS5="socks5h://user:pass@host:port"
```
```bash
# 4. Avvia il server
gunicorn app:app -w 4 --worker-class gevent --worker-connections 100 -b 0.0.0.0:7860 --timeout 120 --keep-alive 5 --max-requests 1000 --max-requests-jitter 100

---

## 🛠️ Gestione Docker

- 📄 Logs: `docker logs -f tvproxy`
- ⛔ Stop: `docker stop tvproxy`
- 🔄 Start: `docker start tvproxy`
- 🧹 Rimozione: `docker rm -f tvproxy`

---

## 🔒 Configurazione Proxy (SOCKS5 / HTTP / HTTPS)

Per accedere a domini specifici che potrebbero essere bloccati (come `newkso.ru`), è ora possibile configurare un proxy. Lo script supporta proxy **SOCKS5**, **HTTP** e **HTTPS** tramite variabili d'ambiente.

La configurazione avviene impostando una delle seguenti variabili d'ambiente prima di avviare lo script o il container Docker.

### 1. Proxy SOCKS5 (Priorità Massima)

Questa è l'opzione consigliata. Se impostata, avrà la precedenza su tutte le altre e verrà usata per tutto il traffico verso i domini protetti.

- **Variabile:** `NEWKSO_PROXY_SOCKS5`
- **Formato:** `socks5h://user:pass@host:port` (o `socks5://...`)

> **Nota:** Per usare i proxy SOCKS5, la dipendenza `requests[socks]` deve essere installata (è già inclusa nel `requirements.txt`).

### 2. Proxy HTTP / HTTPS (Alternativa)

Da usare se non si dispone di un proxy SOCKS5. È possibile impostarne anche solo una.

- **Variabile HTTP:** `NEWKSO_PROXY_HTTP`
- **Formato:** `http://proxy.example.com:8080`
- **Variabile HTTPS:** `NEWKSO_PROXY_HTTPS`
- **Formato:** `https://proxy.example.com:8080`

### 3. Uso di un file `.env` (per Sviluppo Locale)

Per chi esegue lo script localmente (con Python o Gunicorn) senza Docker, un modo comodo per gestire le variabili d'ambiente è usare un file `.env`.

1.  **Crea un file** chiamato `.env` nella directory principale del progetto (la stessa di `app.py`).
2.  **Aggiungi le variabili** al suo interno, una per riga.

**Esempio di file `.env`:**
```
# File .env per la configurazione del proxy
NEWKSO_PROXY_SOCKS5="socks5h://user:pass@host:port"

# Oppure per proxy HTTP/HTTPS
# NEWKSO_PROXY_HTTP="http://proxy.example.com:8080"
# NEWKSO_PROXY_HTTPS="https://proxy.example.com:8080"
```

Lo script caricherà automaticamente queste variabili all'avvio, senza bisogno di usare il comando `export`.

> **Nota:** Il file `.env` non viene considerato quando si usa Docker, a meno che non sia configurato esplicitamente. Per Docker, continua a usare l'opzione `-e` come mostrato negli esempi.

---

### Esempi di Avvio con Proxy

**Con Docker:**
```bash
# Avvia il container Docker passando la variabile d'ambiente per il proxy SOCKS5
docker run -d -p 7860:7860 -e NEWKSO_PROXY_SOCKS5="socks5h://user:pass@host:port" --name tvproxy tvproxy
```

**Con Gunicorn / Python:**
```bash
# Esporta la variabile d'ambiente prima di avviare il server
export NEWKSO_PROXY_SOCKS5="socks5h://user:pass@host:port"
gunicorn app:app -w 4 --worker-class gevent ...
```

## 🛠️ Come Utilizzare

Assicurati di sostituire i placeholder come `<server-ip>` con l'indirizzo IP o l'hostname effettivo del tuo server e `<URL_...>` con gli URL specifici.

---

### 1. Proxy per Liste M3U Complete 📡

Questo endpoint è progettato per proxare l'intera lista M3U. È particolarmente utile per garantire compatibilità e stabilità, con supporto menzionato per formati come Vavoo e Daddylive.

**Formato URL:**
```text
http://<server-ip>:7860/proxy?url=<URL_LISTA_M3U>
```

**Dove:**
-   `<server-ip>`: L'indirizzo IP o hostname del tuo server proxy.
-   `<URL_LISTA_M3U>`: L'URL completo della lista M3U che vuoi proxare.

> 📝 **Nota:** Questo endpoint è ideale per gestire l'intera collezione di flussi contenuta in un file M3U.

---

### 2. Proxy per Singoli Flussi M3U8 (con Headers Personalizzati) 📺✨

Questo endpoint è specifico per proxare singoli flussi video `.m3u8`. La sua caratteristica distintiva è la capacità di inoltrare headers HTTP personalizzati, essenziale per scenari che richiedono autenticazione specifica o per simulare richieste da client particolari.

**Formato URL Base:**
```text
http://<server-ip>:7860/proxy/m3u?url=<URL_FLUSSO_M3U8>
```

**Esempio:**
```text
http://<server-ip>:7860/proxy/m3u?url=https://example.com/stream.m3u8
```

**Dove:**
-   `<server-ip>`: L'indirizzo IP o hostname del tuo server proxy.
-   `<URL_FLUSSO_M3U8>`: L'URL completo del singolo flusso M3U8.

#### 🎯 Aggiungere Headers HTTP Personalizzati (Opzionale)

Per includere headers personalizzati nella richiesta al flusso M3U8, accodali all'URL del proxy. Ogni header deve essere prefissato da `&h_`, seguito dal nome dell'header, un segno di uguale (`=`), e il valore dell'header.

**Formato per gli Headers:**
```text
&h_<NOME_HEADER>=<VALORE_HEADER>
```

**Esempio con Headers Personalizzati:**
```text
http://<server-ip>:7860/proxy/m3u?url=https://example.com/stream.m3u8&h_user-agent=Mozilla/5.0...&h_referer=https://ilovetoplay.xyz/&h_origin=https://ilovetoplay.xyz
```

> ⚠️ **Attenzione:**
> - Ricorda di sostituire `Mozilla/5.0...` con lo User-Agent completo che intendi utilizzare.
> - Se i valori degli header contengono caratteri speciali (es. spazi, due punti), assicurati che siano correttamente URL-encoded per evitare errori.

---

## ✅ Caratteristiche

- 📁 Supporta **.m3u** e **.m3u8** automaticamente
- 🧾 Inoltra gli **HTTP Headers** necessari (Auth, Referer, etc.)
- 🔓 Supera restrizioni geografiche o di accesso
- 🖥️ Compatibile con **qualsiasi player IPTV**
- 🐳 Totalmente dockerizzato, pronto per il deploy
- 🐍 Avviabile anche direttamente con **Python**

---

## 🎉 Fine!

> Ora puoi guardare flussi M3U8 ovunque, senza restrizioni!  
> Enjoy the Stream 🚀
