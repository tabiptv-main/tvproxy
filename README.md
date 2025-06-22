# tvproxy 📺

Un server proxy leggero e dockerizzato basato su **Flask** e **Requests**, progettato per superare restrizioni e accedere a flussi M3U/M3U8 senza interruzioni.

- 📥 **Scarica e modifica** flussi `.m3u` e `.m3u8` al volo.
- 🔁 **Proxa i segmenti** `.ts` mantenendo header personalizzati.
- 🚫 **Supera restrizioni** comuni come `Referer`, `User-Agent`, ecc.
- 🐳 **Facilmente dockerizzabile** su qualsiasi macchina, server o piattaforma cloud.

---

## 📚 Indice

- Piattaforme di Deploy
  - Render
  - HuggingFace
- Setup Locale
  - Docker
  - Termux (Android)
  - Python
- Utilizzo del Proxy
- Configurazione Proxy
- Gestione Docker

---

## ☁️ Piattaforme di Deploy

> ⚠️ **Importante:** Per i canali che lo richiedono (es. DLHD), è **necessario** configurare un proxy **SOCKS5** se non funzionano senza.

### ▶️ Deploy su Render

1.  Vai su **Projects → New → Web Service → Public Git Repo**.
2.  Inserisci l'URL del repository: `https://github.com/nzo66/tvproxy` e clicca **Connect**.
3.  Scegli un nome a piacere per il servizio.
4.  Imposta **Instance Type** su `Free`.
5.  **Configura le variabili d'ambiente per il proxy:**
    *   Nella sezione **Environment**, aggiungi una nuova variabile.
    *   **Key:** `NEWKSO_PROXY_SOCKS5`
    *   **Value:** `socks5h://user:pass@host:port` (sostituisci con i dati del tuo proxy).
6.  Clicca su **Create Web Service**.

### 🤗 Deploy su HuggingFace

1.  Crea un nuovo **Space**.
2.  Scegli un nome, seleziona **Docker** come SDK e lascia la visibilità su **Public**.
3.  Vai su **Files** → `⋮` → **Upload file** e carica il file `DockerfileHF` dal repository, rinominandolo in **Dockerfile**.
4.  **Configura le variabili d'ambiente per il proxy:**
    *   Vai su **Settings** del tuo Space.
    *   Nella sezione **Secrets**, aggiungi un nuovo secret.
    *   **Name:** `NEWKSO_PROXY_SOCKS5`
    *   **Value:** `socks5h://user:pass@host:port` (sostituisci con i dati del tuo proxy).
5.  Una volta completato il deploy, vai su `⋮` → **Embed this Space** per ottenere il **Direct URL**.

> 🔄 **Nota:** Se aggiorni il valore del proxy, ricorda di fare un "Factory Rebuild" dallo Space per applicare le modifiche.

---

## 💻 Setup Locale

### 🐳 Docker (Locale o Server)

#### Costruzione e Avvio

1.  **Clona il repository e costruisci l'immagine Docker:**
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

    *   **Con un proxy SOCKS5:**
        ```bash
        docker run -d -p 7860:7860 -e NEWKSO_PROXY_SOCKS5="socks5h://user:pass@host:port" --name tvproxy tvproxy
        ```
        > ℹ️ Per altri tipi di proxy, consulta la sezione di configurazione.

### 🐧 Termux (Dispositivi Android)

1.  **Installa i pacchetti necessari:**
    ```bash
    pkg update && pkg upgrade
    pkg install git python nano -y
    ```

2.  **Clona il repository e installa le dipendenze:**
    ```bash
    git clone https://github.com/nzo66/tvproxy.git
    cd tvproxy
    pip install -r requirements.txt
    ```

3.  **(Opzionale) Configura un proxy tramite file `.env`:**
    ```bash
    # Crea e apri il file .env con l'editor nano
    nano .env
    ```
    Incolla la riga seguente nel file, sostituendo i dati del tuo proxy. Salva con `Ctrl+X`, poi `Y` e `Invio`.
    ```dotenv
    # Esempio di contenuto per il file .env
    NEWKSO_PROXY_SOCKS5="socks5h://user:pass@host:port"
    ```

4.  **Avvia il server con Gunicorn:**
    ```bash
    gunicorn app:app -w 4 --worker-class gevent -b 0.0.0.0:7860
    ```
    > 👉 **Consiglio:** Per un avvio più robusto, puoi usare i parametri aggiuntivi:
    > ```bash
    > gunicorn app:app -w 4 --worker-class gevent --worker-connections 100 -b 0.0.0.0:7860 --timeout 120 --keep-alive 5 --max-requests 1000 --max-requests-jitter 100
    > ```

### 🐍 Python (Locale)

1.  **Clona il repository:**
    ```bash
    git clone https://github.com/nzo66/tvproxy.git
    cd tvproxy
    ```

2.  **Installa le dipendenze:**
    ```bash
    pip install -r requirements.txt
    ```

3.  **(Opzionale) Configura un proxy tramite file `.env`:**
    Crea un file `.env` nella cartella principale e aggiungi la configurazione del proxy. Lo script lo caricherà automaticamente.
    ```bash
    # Esempio: crea e modifica il file con nano
    nano .env
    ```
    **Contenuto del file `.env`:**
    ```dotenv
    NEWKSO_PROXY_SOCKS5="socks5h://user:pass@host:port"
    ```

4.  **Avvia il server con Gunicorn:**
    ```bash
    gunicorn app:app -w 4 --worker-class gevent --worker-connections 100 -b 0.0.0.0:7860 --timeout 120 --keep-alive 5 --max-requests 1000 --max-requests-jitter 100
    ```

---

## 🛠️ Come Utilizzare

Sostituisci `<server-ip>` con l'IP o l'hostname del tuo server e `<URL_...>` con gli URL che vuoi proxare.

### 📡 Endpoint 1: Proxy per Liste M3U Complete

Ideale per proxare un'intera lista M3U, garantendo compatibilità con vari formati (es. Vavoo, Daddylive).

**Formato URL:**
```text
http://<server-ip>:7860/proxy?url=<URL_LISTA_M3U>
```

### 📺 Endpoint 2: Proxy per Singoli Flussi M3U8 (con Headers)

Specifico per proxare un singolo flusso `.m3u8`, con la possibilità di aggiungere headers HTTP personalizzati per superare protezioni specifiche.

**Formato URL Base:**
```text
http://<server-ip>:7860/proxy/m3u?url=<URL_FLUSSO_M3U8>
```

**Aggiungere Headers Personalizzati (Opzionale):**
Per aggiungere headers, accodali all'URL usando il prefisso `&h_`.

**Formato:**
```text
&h_<NOME_HEADER>=<VALORE_HEADER>
```

**Esempio completo con Headers:**
```text
http://<server-ip>:7860/proxy/m3u?url=https://example.com/stream.m3u8&h_user-agent=VLC/3.0.20&h_referer=https://example.com/
```

> ⚠️ **Attenzione:** Se i valori degli header contengono caratteri speciali, assicurati che siano correttamente **URL-encoded**.

---

## 🔒 Configurazione Proxy

Lo script può utilizzare un proxy per accedere a domini bloccati. La configurazione avviene tramite variabili d'ambiente o un file `.env` (solo per uso locale).

### Priorità e Tipi di Proxy

1.  **SOCKS5 (Consigliato):** Massima priorità. Usato per tutto il traffico verso i domini protetti.
    -   **Variabile:** `NEWKSO_PROXY_SOCKS5`
    -   **Formato:** `socks5h://user:pass@host:port`

2.  **HTTP / HTTPS:** Alternativa se non hai un proxy SOCKS5.
    -   **Variabile HTTP:** `NEWKSO_PROXY_HTTP`
    -   **Formato:** `http://proxy.example.com:8080`
    -   **Variabile HTTPS:** `NEWKSO_PROXY_HTTPS`
    -   **Formato:** `https://proxy.example.com:8080`

### Uso del file `.env` (Sviluppo Locale)

Per l'uso con Python o Gunicorn (non Docker), crea un file `.env` nella directory principale.

**Esempio di file `.env`:**
```dotenv
# File .env per la configurazione del proxy
NEWKSO_PROXY_SOCKS5="socks5h://user:pass@host:port"

# Oppure per proxy HTTP/HTTPS (commentati)
# NEWKSO_PROXY_HTTP="http://proxy.example.com:8080"
# NEWKSO_PROXY_HTTPS="https://proxy.example.com:8080"
```
> ℹ️ Lo script caricherà automaticamente queste variabili. Per Docker, usa sempre l'opzione `-e`.

---

## 🐳 Gestione Docker

-   **Visualizza i log:** `docker logs -f tvproxy`
-   **Ferma il container:** `docker stop tvproxy`
-   **Avvia il container:** `docker start tvproxy`
-   **Rimuovi il container:** `docker rm -f tvproxy`

---

## ✅ Caratteristiche Principali

-   ✅ Supporto automatico per `.m3u` e `.m3u8`.
-   ✅ Inoltro di headers HTTP personalizzati (`Authorization`, `Referer`, etc.).
-   ✅ Superamento di restrizioni geografiche o di accesso.
-   ✅ Compatibilità con qualsiasi player IPTV.
-   ✅ Totalmente dockerizzato e pronto per il deploy.
-   ✅ Avviabile anche direttamente con Python.

---

## 🎉 Enjoy the Stream!

> Ora puoi guardare i tuoi flussi preferiti ovunque, senza restrizioni.

<!--
[PROMPT_SUGGESTION]Traduci questo file README in inglese.[/PROMPT_SUGGESTION]
[PROMPT_SUGGESTION]Crea uno script di avvio (`start.sh`) che semplifichi l'esecuzione dei comandi Gunicorn.[/PROMPT_SUGGESTION]
-->

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
