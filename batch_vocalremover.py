"""Upload audio files to VocalRemover.org and save only the isolated voice."""

from __future__ import annotations

import re
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


SITE = "https://vocalremover.org/"
# Set either value to a fixed folder to skip that folder picker, for example:
# INPUT_DIR = Path(r"D:\Audio\Da elaborare")
# OUTPUT_DIR = Path(r"D:\Audio\Voci isolate")
INPUT_DIR: Path | None = Path(r"C:/Users/stefa/Documents/Audacity/grezzi")
OUTPUT_DIR: Path | None = Path(r"C:/Users/stefa/Documents/Audacity")
# Delete each source file only after its output has downloaded successfully
# and the site has cleared that conversion.
DELETE_SOURCE_AFTER_SUCCESS = True
PROCESSING_TIMEOUT_SECONDS = 30
MAX_FILE_ATTEMPTS = 2  # first try plus one retry after reloading the page
AUDIO_EXTENSIONS = {
    ".aac", ".aif", ".aiff", ".flac", ".m4a", ".mp3", ".ogg",
    ".opus", ".wav", ".wma",
}
SAVE_RE = re.compile(r"^save$", re.IGNORECASE)
VOCAL_MENU_RE = re.compile(r"^(?:vocal|vocals|voce)$", re.IGNORECASE)
BROWSE_RE = re.compile(r"browse\s+my\s+files", re.IGNORECASE)
CLOSE_RE = re.compile(r"^(?:close|chiudi|×|✕|x)$", re.IGNORECASE)
DELETE_CONFIRM_RE = re.compile(r"^(?:yes|yes,\s*delete)$", re.IGNORECASE)


class BrowseButtonMissingError(RuntimeError):
    pass


class ProcessingWaitTimeoutError(RuntimeError):
    pass


def choose_folder(title: str) -> Path | None:
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    selected = filedialog.askdirectory(title=title, mustexist=True)
    root.destroy()
    return Path(selected) if selected else None


def configured_folder(folder: Path | None, title: str) -> Path | None:
    if folder is None:
        return choose_folder(title)
    folder = folder.expanduser()
    if not folder.is_dir():
        print(f"La cartella configurata non esiste: {folder}")
        return None
    return folder


def visible_control_names(page) -> list[str]:
    return [
        name.strip()
        for name in page.locator("button, [role='menuitem'], a").all_text_contents()
        if name.strip()
    ]


def browse_control(page):
    # Prefer the button's rendered text; the site's accessible name can differ
    # even though the button visibly says "Browse my files".
    control = page.locator("button").filter(has_text=BROWSE_RE)
    if control.count() == 0:
        control = page.get_by_role("button", name=BROWSE_RE)
    if control.count() == 0:
        control = page.get_by_text(BROWSE_RE, exact=False)
    if control.count() == 0:
        raise BrowseButtonMissingError(
            "Non trovo il pulsante Browse my files. "
            f"Controlli visibili: {visible_control_names(page)}"
        )
    return control.first


def wait_for_upload_page(page):
    browse = page.locator("button").filter(has_text=BROWSE_RE).first
    try:
        browse.wait_for(timeout=30000)
    except PlaywrightTimeoutError as error:
        raise BrowseButtonMissingError(
            "Non trovo il pulsante Browse my files dopo aver atteso il caricamento. "
            f"Controlli visibili: {visible_control_names(page)}"
        ) from error
    return browse_control(page)


def restart_page(page) -> None:
    print("  Ricarico VocalRemover...")
    page.goto(SITE, wait_until="domcontentloaded")
    wait_for_upload_page(page)


def save_voice_file(page, source: Path, output_dir: Path) -> Path:
    save_button = page.get_by_role("button", name=SAVE_RE)
    if save_button.count() == 0:
        raise RuntimeError(
            "Non trovo il pulsante Save. "
            f"Controlli visibili: {visible_control_names(page)}"
        )
    save_button.first.click()

    # Save apre la tendina; Vocal avvia il download della traccia isolata.
    vocal_choice = page.get_by_role("menuitem", name=VOCAL_MENU_RE)
    if vocal_choice.count() == 0:
        vocal_choice = page.get_by_role("button", name=VOCAL_MENU_RE)
    if vocal_choice.count() == 0:
        vocal_choice = page.get_by_text(VOCAL_MENU_RE, exact=True)
    if vocal_choice.count() == 0:
        raise RuntimeError(
            "Ho aperto Save ma non trovo la voce Vocal nella tendina. "
            f"Controlli visibili: {visible_control_names(page)}"
        )

    with page.expect_download(timeout=30000) as pending_download:
        vocal_choice.first.click()
    download = pending_download.value

    downloaded_ext = Path(download.suggested_filename).suffix or source.suffix
    target = output_dir / f"{source.stem}{downloaded_ext}"
    download.save_as(target)
    return target


def return_to_upload(page) -> None:
    # The close button is an unlabeled icon in the result player.
    close_buttons = page.locator("div.player-cancel > button")
    if close_buttons.count() == 0:
        close_buttons = page.get_by_role("button", name=CLOSE_RE)
    if close_buttons.count() == 0:
        raise RuntimeError(
            "Non trovo il pulsante X per chiudere il risultato. "
            f"Controlli visibili: {visible_control_names(page)}"
        )

    close_buttons.last.click(timeout=5000)
    confirm = page.locator('button.red[aria-label="yes"]')
    if confirm.count() == 0:
        confirm = page.get_by_role("button", name=DELETE_CONFIRM_RE)
    if confirm.count() == 0:
        confirm = page.get_by_text(re.compile(r"yes,\s*delete", re.IGNORECASE), exact=True)
    confirm.wait_for(timeout=10000)
    confirm.first.click()
    try:
        wait_for_upload_page(page)
    except BrowseButtonMissingError:
        # The conversion has already been downloaded, so just reset the page;
        # do not process the same source again.
        restart_page(page)


def process_file(page, source: Path, output_dir: Path) -> Path:
    with page.expect_file_chooser(timeout=10000) as chooser_info:
        wait_for_upload_page(page).click()
    chooser_info.value.set_files(str(source))

    try:
        page.get_by_role("button", name=SAVE_RE).wait_for(
            timeout=PROCESSING_TIMEOUT_SECONDS * 1000
        )
    except PlaywrightTimeoutError as error:
        raise ProcessingWaitTimeoutError(
            f"Save non è comparso entro {PROCESSING_TIMEOUT_SECONDS} secondi."
        ) from error
    return save_voice_file(page, source, output_dir)


def process_file_with_retry(page, source: Path, output_dir: Path) -> Path:
    for attempt in range(1, MAX_FILE_ATTEMPTS + 1):
        try:
            return process_file(page, source, output_dir)
        except (BrowseButtonMissingError, ProcessingWaitTimeoutError) as error:
            if attempt >= MAX_FILE_ATTEMPTS:
                raise
            print(f"  {error} Riprovo ({attempt + 1}/{MAX_FILE_ATTEMPTS}).")
            restart_page(page)
    raise RuntimeError("Tentativi esauriti senza elaborare il file.")


def delete_source_after_success(source: Path, input_dir: Path, saved: Path) -> None:
    if not saved.is_file() or saved.stat().st_size == 0:
        raise RuntimeError(f"Output assente o vuoto; mantengo il sorgente: {saved}")
    source_resolved = source.resolve()
    if source_resolved.parent != input_dir.resolve():
        raise RuntimeError(f"Il sorgente non è un file diretto della cartella input: {source}")
    source.unlink()
    print(f"  Sorgente eliminato: {source.name}")


def main() -> int:
    input_dir = configured_folder(INPUT_DIR, "Seleziona la cartella con i file audio")
    if input_dir is None:
        print("Selezione cartella input annullata.")
        return 1

    output_dir = configured_folder(OUTPUT_DIR, "Seleziona la cartella in cui salvare le voci")
    if output_dir is None:
        print("Selezione cartella output annullata.")
        return 1
    if DELETE_SOURCE_AFTER_SUCCESS and input_dir.resolve() == output_dir.resolve():
        print("Input e output devono essere cartelle diverse se si elimina il sorgente.")
        return 1

    files = sorted(
        path for path in input_dir.iterdir()
        if path.is_file() and path.suffix.lower() in AUDIO_EXTENSIONS
    )
    if not files:
        print(f"Nessun file audio supportato trovato in: {input_dir}")
        return 1

    pending = [path for path in files if not list(output_dir.glob(f"{path.stem}.*"))]
    print(f"Trovati {len(files)} file; da elaborare: {len(pending)}.")
    if not pending:
        print("Tutti i file sembrano già elaborati.")
        return 0

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()
        page.goto(SITE, wait_until="domcontentloaded")

        failures: list[tuple[Path, str]] = []
        for index, source in enumerate(pending, start=1):
            print(f"[{index}/{len(pending)}] {source.name}")
            try:
                saved = process_file_with_retry(page, source, output_dir)
                print(f"  Salvato: {saved.name}")
                return_to_upload(page)
                if DELETE_SOURCE_AFTER_SUCCESS:
                    delete_source_after_success(source, input_dir, saved)
            except Exception as error:
                failures.append((source, str(error)))
                print(f"  ERRORE: {error}")
                # Leave the browser open so the user can inspect the page.
                input("Sistema o chiudi la schermata nel browser, poi premi Invio per continuare...")
                if index < len(pending):
                    try:
                        upload = browse_control(page)
                        upload_ready = upload.is_visible()
                    except Exception:
                        upload_ready = False
                    if not upload_ready:
                        try:
                            return_to_upload(page)
                        except Exception as reset_error:
                            failures.append((source, f"Ripristino pagina: {reset_error}"))
                            break

        context.close()
        browser.close()

    if failures:
        print("\nFile con problemi:")
        for source, error in failures:
            print(f"- {source.name}: {error}")
        return 2

    print("\nElaborazione completata.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nInterrotto dall'utente.")
        raise SystemExit(130)
