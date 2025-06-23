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

### ▶️ Deploy su Render

1.  Vai su **Projects → New → Web Service → Public Git Repo**.
2.  Inserisci l'URL del repository: `https://github.com/nzo66/tvproxy` e clicca **Connect**.
3.  Scegli un nome a piacere per il servizio.
4.  Imposta **Instance Type** su `Free` (o un'opzione a pagamento per prestazioni migliori).
5.  **(Opzionale) Configura le variabili d'ambiente per i proxy:**
    *   Nella sezione **Environment**, aggiungi una nuova variabile.
    *   **Key:** `NEWKSO_PROXY` (o `VAVOO_PROXY`, `GENERAL_PROXY`).
    *   **Value:** `socks5://user:pass@host:port` (sostituisci con i dati del tuo proxy `http`, `https` o `socks5`).
    *   **Nota:** Puoi inserire più proxy separandoli da una virgola (es. `http://proxy1,socks5://proxy2`). Lo script ne sceglierà uno a caso.
    *   Per maggiori dettagli, consulta la sezione Configurazione Proxy.
6.  Clicca su **Create Web Service**.

### 🤗 Deploy su HuggingFace

1.  Crea un nuovo **Space**.
2.  Scegli un nome, seleziona **Docker** come SDK e lascia la visibilità su **Public**.
3.  Vai su **Files** → `⋮` → **Upload file** e carica il file `DockerfileHF` dal repository, rinominandolo in **Dockerfile**.
4.  **(Opzionale) Configura le variabili d'ambiente per i proxy:**
    *   Vai su **Settings** del tuo Space.
    *   Nella sezione **Secrets**, aggiungi un nuovo secret.
    *   **Name:** `NEWKSO_PROXY` (o `VAVOO_PROXY`, `GENERAL_PROXY`).
    *   **Value:** `socks5://proxy1,http://proxy2` (sostituisci con i dati dei tuoi proxy).
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

    *   **Con un proxy:**
        ```bash
        docker run -d -p 7860:7860 -e NEWKSO_PROXY="socks5://proxy1,http://proxy2" --name tvproxy tvproxy
        ```
        > ℹ️ Per configurare altri proxy (Vavoo, Generale), aggiungi altre variabili `-e`. Consulta la sezione di configurazione.

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
    # Esempio di configurazione proxy nel file .env
    NEWKSO_PROXY="socks5://user:pass@host1:port"
    VAVOO_PROXY="http://user:pass@host2:port"
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
    # Proxy per newkso.ru e siti correlati
    NEWKSO_PROXY="socks5://proxy1:1080,socks5://user:pass@proxy2:1080"
    NEWKSO_SSL_VERIFY=false
    # Aggiungi qui altre configurazioni (VAVOO_PROXY, GENERAL_PROXY)
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

Lo script supporta una configurazione proxy flessibile per gestire l'accesso a diversi domini. La configurazione avviene tramite variabili d'ambiente o un file `.env`.

### Logica di Priorità

Il proxy viene selezionato con la seguente priorità:
1.  **Proxy Specifico per Dominio:** Se l'URL corrisponde a un dominio con un proxy dedicato (es. `newkso.ru`, `vavoo.to`), viene usato quel proxy.
2.  **Proxy Generale:** Se non corrisponde a nessun dominio specifico e un proxy generale è configurato, viene usato quest'ultimo.
3.  **Nessun Proxy:** Se nessuna delle condizioni sopra è soddisfatta, la richiesta viene effettuata direttamente.

### Variabili d'Ambiente

| Variabile            | Descrizione                                                                                              | Esempio                                            |
| -------------------- | -------------------------------------------------------------------------------------------------------- | -------------------------------------------------- |
| `NEWKSO_PROXY`       | Proxy per `newkso.ru` e siti correlati (Daddy).                                                          | `socks5://user:pass@host:port`                     |
| `NEWKSO_SSL_VERIFY`  | Verifica SSL per `newkso`. **Default: `false`**.                                                          | `false`                                            |
| `VAVOO_PROXY`        | Proxy dedicato per i domini `vavoo.to`.                                                                  | `http://user:pass@host:port`                       |
| `VAVOO_SSL_VERIFY`   | Verifica SSL per `vavoo.to`. **Default: `true`**.                                                          | `true`                                             |
| `GENERAL_PROXY`      | Proxy di fallback per tutto il traffico non coperto dai proxy specifici. Lasciare vuoto per disabilitarlo. | `socks5://user:pass@host:port`                     |
| `GENERAL_SSL_VERIFY` | Verifica SSL per il proxy generale. **Default: `true`**.                                                   | `true`                                             |

> **Nota:** Tutti i campi proxy (`*_PROXY`) supportano i formati `http`, `https`, `socks5` e `socks5h`. Puoi anche specificare una **lista di proxy separati da virgola**; lo script ne sceglierà uno a caso per ogni richiesta.

### Esempio di file `.env` (per uso locale)

Crea un file `.env` nella directory principale del progetto per configurare facilmente i proxy durante lo sviluppo locale.

```dotenv
# Proxy per newkso.ru (con verifica SSL disabilitata)
NEWKSO_PROXY="socks5://user:pass@host1:port"
NEWKSO_SSL_VERIFY=false

# Proxy per i domini vavoo.to
VAVOO_PROXY="http://user:pass@host2:port"
VAVOO_SSL_VERIFY=true

# Proxy generico per tutte le altre richieste
GENERAL_PROXY="socks5://user:pass@host3:port"
GENERAL_SSL_VERIFY=true
```

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
