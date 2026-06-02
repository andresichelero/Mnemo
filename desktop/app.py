import customtkinter as ctk
import sys
import os

# Ensure desktop is in path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from desktop.components.topbar import TopBar
from desktop.components.statusbar import StatusBar
from desktop.views.sidebar import Sidebar
from desktop.views.gallery import GalleryView
from desktop.views.detail_panel import DetailPanel
from desktop.views.settings_panel import SettingsPanel
import threading
from tkinterdnd2 import TkinterDnD, DND_FILES

class CTkDnDApp(ctk.CTk, TkinterDnD.DnDWrapper):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.TkdndVersion = TkinterDnD._require(self)

class MnemoApp(CTkDnDApp):
    def __init__(self, client):
        super().__init__()
        self.client = client
        
        self.title("Mnemo")
        self.geometry("1200x800")
        self.minsize(800, 600)
        
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        
        # Grid layout
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(1, weight=1)
        
        # Current filters
        self.current_filters = {}
        
        # Components
        self.topbar = TopBar(self, search_callback=self._on_search, open_settings_callback=self._open_settings)
        self.topbar.grid(row=0, column=0, columnspan=3, sticky="ew")
        
        self.sidebar = Sidebar(self, self.client, filter_callback=self._on_filter)
        self.sidebar.grid(row=1, column=0, sticky="ns")
        
        self.center_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.center_frame.grid(row=1, column=1, sticky="nsew", padx=10, pady=10)
        
        self.bulk_bar = ctk.CTkFrame(self.center_frame, height=40, fg_color=("gray75", "gray25"))
        self.bulk_bar_label = ctk.CTkLabel(self.bulk_bar, text="0 items selected")
        self.bulk_bar_label.pack(side="left", padx=10, pady=5)
        
        self.bulk_folder_var = ctk.StringVar(value="Select Folder")
        self.bulk_folder_menu = ctk.CTkOptionMenu(self.bulk_bar, variable=self.bulk_folder_var, values=["Select Folder"])
        self.bulk_folder_menu.pack(side="left", padx=5, pady=5)
        
        self.bulk_move_btn = ctk.CTkButton(self.bulk_bar, text="Move Selected", command=self._bulk_move)
        self.bulk_move_btn.pack(side="left", padx=5, pady=5)
        
        self.gallery = GalleryView(self.center_frame, self.client, on_item_click=self._on_gallery_item_click, on_selection_change=self._on_selection_change)
        self.gallery.pack(expand=True, fill="both")
        
        self.detail_panel = DetailPanel(self, self.client)
        self.detail_panel.grid(row=1, column=2, sticky="ns")
        
        self.statusbar = StatusBar(self, self.client)
        self.statusbar.grid(row=2, column=0, columnspan=3, sticky="ew")
        
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # Drag and Drop
        self.drop_target_register(DND_FILES)
        self.dnd_bind('<<Drop>>', self.drop_files)
        
        # Load initial data
        self.after(100, self._initial_load)
        
    def drop_files(self, event):
        files = self.tk.splitlist(event.data)
        for f in files:
            threading.Thread(target=self._upload_and_refresh, args=(f,), daemon=True).start()
            
    def manual_upload(self):
        from customtkinter import filedialog
        files = filedialog.askopenfilenames(title="Select Images to Upload", filetypes=[("Images", "*.png;*.jpg;*.jpeg;*.webp")])
        if files:
            for f in files:
                threading.Thread(target=self._upload_and_refresh, args=(f,), daemon=True).start()
            
    def _upload_and_refresh(self, file_path):
        res = self.client.upload_image(file_path)
        if "error" not in res:
            folder_id = self.current_filters.get("folder_id")
            if folder_id:
                self.client.update_screenshot_folders(res["id"], [folder_id])
            self.after(0, self._load_gallery)
        else:
            print("Upload error:", res)
            
    def _initial_load(self):
        self.sidebar.load_folders()
        self._load_gallery()
        
    def _load_gallery(self):
        def fetch():
            res = self.client.get_screenshots(limit=100, filters=self.current_filters)
            self.after(0, self._update_gallery_ui, res)
        threading.Thread(target=fetch, daemon=True).start()

    def _update_gallery_ui(self, res):
        if "error" not in res and "items" in res:
            self.gallery.set_items(res["items"])
            self._on_selection_change([])
        elif isinstance(res, list): # fallback depending on API response format
            self.gallery.set_items(res)
            self._on_selection_change([])
            
    def _on_search(self, query):
        if query:
            def search_fetch():
                res = self.client.search(query, limit=50)
                self.after(0, self._update_gallery_ui, res)
            threading.Thread(target=search_fetch, daemon=True).start()
        else:
            self._load_gallery()
            
    def _on_filter(self, filters):
        if filters:
            self.current_filters.update(filters)
        else:
            self.current_filters = {}
        self._load_gallery()
        
    def _on_selection_change(self, selected_ids):
        self.selected_ids = selected_ids
        if len(selected_ids) > 0:
            self.bulk_bar_label.configure(text=f"{len(selected_ids)} items selected")
            # Update folder list
            if hasattr(self.sidebar, "folders"):
                names = [f["name"] for f in self.sidebar.folders]
                if names:
                    self.bulk_folder_menu.configure(values=names)
            self.bulk_bar.pack(fill="x", side="top", pady=(0, 10))
        else:
            self.bulk_bar.pack_forget()
            
    def _bulk_move(self):
        if not hasattr(self, 'selected_ids') or not self.selected_ids:
            return
            
        name = self.bulk_folder_var.get()
        target_id = None
        for f in self.sidebar.folders:
            if f["name"] == name:
                target_id = f["id"]
                break
                
        if target_id:
            def assign_all():
                for sid in self.selected_ids:
                    self.client.update_screenshot_folders(sid, [target_id])
                self.after(0, lambda: self.bulk_move_btn.configure(text="Moved!"))
                self.after(2000, lambda: self.bulk_move_btn.configure(text="Move Selected"))
                self.after(2000, self._load_gallery) # reload to reflect changes
                
            self.bulk_move_btn.configure(text="Moving...")
            threading.Thread(target=assign_all, daemon=True).start()
        
    def _on_gallery_item_click(self, screenshot_data):
        self.detail_panel.load_item(screenshot_data)
        
    def _open_settings(self):
        SettingsPanel(self, self.client)
        
    def on_closing(self):
        self.client.close()
        self.destroy()
