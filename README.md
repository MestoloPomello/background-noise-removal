# VocalRemover batch

Prototipo Windows per caricare in sequenza i file audio di una cartella su VocalRemover.org e scaricare la traccia con la sola voce. Per ogni file clicca `Browse my files`, seleziona il file, attende la fine dell'elaborazione, apre `Save` e seleziona `Vocal`. Poi chiude il risultato con la X e conferma `Yes, delete` per passare al file successivo.

## Avvio

1. Installa Python 3.10 o successivo.
2. Apri PowerShell in questa cartella ed esegui:

   ```powershell
   py -m pip install -r requirements.txt
   py -m playwright install chromium
   py batch_vocalremover.py
   ```

3. Scegli le cartelle di input e output nei selettori che appaiono.
4. Lascia aperta la finestra del browser mentre lo script lavora.

## Cartelle fisse (facoltativo)

In `batch_vocalremover.py`, in cima al file, puoi impostare `INPUT_DIR` e/o `OUTPUT_DIR` con percorsi fissi. Per esempio:

```python
INPUT_DIR = Path(r"D:\Audio\Da elaborare")
OUTPUT_DIR = Path(r"D:\Audio\Voci isolate")
```

Se una variabile resta `None`, lo script mostrerà il selettore per quella cartella. Le cartelle configurate devono già esistere.

## Retry automatico

Se non trova `Browse my files`, oppure `Save` non compare entro 30 secondi, lo script ricarica la pagina e riprova il file una volta. Puoi modificare `PROCESSING_TIMEOUT_SECONDS` e `MAX_FILE_ATTEMPTS` in cima a `batch_vocalremover.py`.

## Pulizia dei file sorgente

`DELETE_SOURCE_AFTER_SUCCESS = True` elimina il file originale dalla cartella input solo dopo che il risultato è stato scaricato, verificato come non vuoto e la conversione è stata cancellata dal sito. Input e output devono essere cartelle diverse. Imposta il valore a `False` per conservare gli originali. I file saltati perché il risultato esisteva già non vengono eliminati.

I risultati vengono salvati come `nomefile.<formato>`. Quelli già presenti vengono saltati. Il prototipo elabora un file alla volta.

## Nota sul primo avvio

I testi dei pulsanti e la schermata di risultato possono cambiare con la lingua o con gli aggiornamenti del sito. Se il prototipo non riconosce `Save` o `Vocal`, lascia aperta la pagina e riporta il messaggio d'errore e i nomi dei controlli che stampa il programma: serviranno per adattare i selettori.
